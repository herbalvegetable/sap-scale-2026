from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.config import Settings
from app.models.schemas import EvidenceItem, FactorScore, RiskScore
from app.services.ai_core_client import AICoreClient, AICoreError
from app.services.confidence_assessor import attach_confidence
from app.services.presentable import source_label, yes_no
from app.services.privacy import redact_for_llm
from app.services.repository import RiskRepository

logger = logging.getLogger(__name__)


FACTOR_LIMITS = {
    "entity_risk": ("Entity risk profile", 25.0),
    "transaction_behaviour": ("Transaction behaviour", 25.0),
    "geographic_risk": ("Geographic risk", 20.0),
    "behavioural_deviation": ("Behavioural deviation", 15.0),
    "regulatory_sensitivity": ("Regulatory sensitivity", 15.0),
}


class ModelFactor(BaseModel):
    score: float = Field(ge=0)
    rationale: str = Field(min_length=5, max_length=800)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ModelScoreResponse(BaseModel):
    entity_risk: ModelFactor
    transaction_behaviour: ModelFactor
    geographic_risk: ModelFactor
    behavioural_deviation: ModelFactor
    regulatory_sensitivity: ModelFactor

    @model_validator(mode="after")
    def enforce_factor_limits(self) -> "ModelScoreResponse":
        for key, (_, maximum) in FACTOR_LIMITS.items():
            if getattr(self, key).score > maximum:
                raise ValueError(f"{key} exceeds {maximum}")
        return self


SCORING_SYSTEM_PROMPT = """
You are a conservative financial-crime alert triage assistant. Assess only the
facts supplied in the JSON payload. Never infer guilt, protected traits, or facts
not present. Return JSON only with exactly these keys: entity_risk,
transaction_behaviour, geographic_risk, behavioural_deviation, and
regulatory_sensitivity. Each key must contain score, rationale, and evidence.
Evidence is an array of objects containing label, value, and source.

Maximum scores are 25, 25, 20, 15, and 15 respectively. Use the full range but
do not treat missing data as evidence of risk. Sanctions or confirmed PEP data
belongs under entity risk; size/structuring/speed under transaction behaviour;
FATF/country exposure under geographic risk; deviation from the supplied
baseline under behavioural deviation; supervisory attention and prior cases
under regulatory sensitivity. Write every rationale and evidence value in plain
English suitable for an executive reader — no snake_case keys, no key=value dumps,
and use friendly source names such as “Company risk profiles”.
""".strip()


class ScoringEngine:
    def __init__(self, settings: Settings, repository: RiskRepository, ai_core: AICoreClient) -> None:
        self.settings = settings
        self.repository = repository
        self.ai_core = ai_core

    @staticmethod
    def source_fingerprint(context: dict[str, Any]) -> str:
        encoded = json.dumps(context, default=str, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:20]

    @staticmethod
    def tier_for(total: float) -> str:
        if total >= 67:
            return "high"
        if total >= 34:
            return "medium"
        return "low"

    def score_alert(self, alert_id: str, refresh: bool = False, use_ai: bool = True) -> RiskScore:
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)
        fingerprint = self.source_fingerprint(context)
        cached = self.repository.get_score(alert_id)
        # Always reuse a matching cached score so list, detail, and stats stay consistent.
        # AI recomputation is reserved for explicit refresh=True.
        if cached and cached.source_fingerprint == fingerprint and not refresh:
            return cached.model_copy(update={"provenance": "cached"})

        if use_ai:
            try:
                response = ModelScoreResponse.model_validate(
                    self.ai_core.chat_json(SCORING_SYSTEM_PROMPT, self._prompt_payload(context))
                )
                factors = self._model_factors(response)
                provenance = "ai"
                model = self.settings.aicore_model_name
            except (AICoreError, ValidationError, ValueError, KeyError) as exc:
                logger.warning("AI factor scoring failed; using deterministic fallback: %s", exc)
                factors = self._fallback_factors(context)
                provenance = "fallback"
                model = "deterministic-fallback-v1"
        else:
            factors = self._fallback_factors(context)
            provenance = "fallback"
            model = "deterministic-fallback-v1"

        factors, overall_confidence = attach_confidence(factors, context)
        total = round(sum(factor.score for factor in factors), 1)
        score = RiskScore(
            alert_id=alert_id,
            total=total,
            tier=self.tier_for(total),
            factors=factors,
            confidence=overall_confidence,
            provenance=provenance,
            model=model,
            prompt_version=self.settings.prompt_version,
            generated_at=datetime.now(timezone.utc),
            source_fingerprint=fingerprint,
        )
        self.repository.save_score(score)
        return score

    @staticmethod
    def _prompt_payload(context: dict[str, Any]) -> dict[str, Any]:
        return redact_for_llm(
            {
                "alert": {
                    "id": context["id"],
                    "type": context["alert_type"],
                    "description": context["description"],
                    "status": context["status"],
                },
                "transaction": {
                    "amount": context["amount"],
                    "currency": context["currency"],
                    "origin_country": context["origin_country"],
                    "destination_country": context["destination_country"],
                    **context["transaction"],
                },
                "company_name": context.get("company_name"),
                "company": context["company"],
                "derived_signals": context["signals"],
            }
        )

    @staticmethod
    def _model_factors(response: ModelScoreResponse) -> list[FactorScore]:
        factors: list[FactorScore] = []
        for key, (label, maximum) in FACTOR_LIMITS.items():
            item = getattr(response, key)
            factors.append(
                FactorScore(
                    key=key,
                    label=label,
                    score=round(item.score, 1),
                    max_score=maximum,
                    rationale=item.rationale,
                    evidence=item.evidence,
                )
            )
        return factors

    @staticmethod
    def _fallback_factors(context: dict[str, Any]) -> list[FactorScore]:
        company = context["company"]
        signals = context["signals"]

        entity = min(
            25.0,
            (15 if company["sanctions_match"] else 0)
            + (6 if company["pep"] else 0)
            + min(4, max(0, company["beneficial_owner_layers"] - 1)),
        )
        behaviour = min(
            25.0,
            min(13, max(0, (signals["amount_ratio"] - 1) * 3))
            + min(9, signals["rapid_transfers"] * 3)
            + (3 if "structur" in context["alert_type"].lower() else 0),
        )
        geo_map = {"high": 18.0, "medium": 10.0, "low": 3.0, "unknown": 5.0}
        geography = geo_map.get(str(signals["fatf_risk"]).lower(), 5.0)
        if signals["new_corridor"]:
            geography = min(20, geography + 2)
        deviation = min(15.0, max(0, (signals["amount_ratio"] - 1) * 3) + (4 if signals["new_corridor"] else 0))
        regulatory = min(
            15.0,
            (6 if signals["supervisory_attention"] else 0) + min(9, company["prior_cases"] * 3),
        )

        rows = [
            (
                "entity_risk",
                entity,
                (
                    f"Entity screening shows sanctions match: {yes_no(company['sanctions_match'])}, "
                    f"PEP association: {yes_no(company['pep'])}, and "
                    f"{company['beneficial_owner_layers']} ownership layers."
                ),
                [
                    EvidenceItem(
                        label="Risk rating",
                        value=str(company["risk_rating"]).title(),
                        source=source_label("COMPANY_RISK_PROFILES"),
                    )
                ],
            ),
            (
                "transaction_behaviour",
                behaviour,
                (
                    f"Amount is {signals['amount_ratio']:.1f}× baseline with "
                    f"{signals['rapid_transfers']} rapid related transfers."
                ),
                [
                    EvidenceItem(
                        label="Transaction amount",
                        value=f"{context['currency']} {context['amount']:,.0f}",
                        source=source_label("TRANSACTIONS"),
                    )
                ],
            ),
            (
                "geographic_risk",
                geography,
                (
                    f"Destination country risk is {str(signals['fatf_risk']).title()}; "
                    f"new corridor: {yes_no(signals['new_corridor'])}."
                ),
                [
                    EvidenceItem(
                        label="Destination",
                        value=str(context["destination_country"]),
                        source=source_label("COUNTRIES"),
                    )
                ],
            ),
            (
                "behavioural_deviation",
                deviation,
                f"Current amount is {signals['amount_ratio']:.1f}× the entity's normal amount.",
                [
                    EvidenceItem(
                        label="Baseline average",
                        value=f"{context['currency']} {company['baseline_average_amount']:,.0f}",
                        source=source_label("TRANSACTION_BASELINES"),
                    )
                ],
            ),
            (
                "regulatory_sensitivity",
                regulatory,
                (
                    f"Supervisory attention: {yes_no(signals['supervisory_attention'])}; "
                    f"prior compliance cases: {company['prior_cases']}."
                ),
                [
                    EvidenceItem(
                        label="Prior cases",
                        value=str(company["prior_cases"]),
                        source=source_label("COMPLIANCE_CASES"),
                    )
                ],
            ),
        ]
        return [
            FactorScore(
                key=key,
                label=FACTOR_LIMITS[key][0],
                score=round(score, 1),
                max_score=FACTOR_LIMITS[key][1],
                rationale=rationale,
                evidence=evidence,
            )
            for key, score, rationale, evidence in rows
        ]
