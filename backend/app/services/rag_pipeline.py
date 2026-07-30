from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models.schemas import EvidenceItem, Explanation
from app.services.ai_core_client import AICoreClient, AICoreError
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore

logger = logging.getLogger(__name__)


class ModelExplanation(BaseModel):
    summary: str = Field(min_length=20, max_length=1200)
    key_drivers: list[str] = Field(min_length=1, max_length=6)
    mitigating_factors: list[str] = Field(max_length=5)
    recommended_checks: list[str] = Field(min_length=1, max_length=6)
    limitations: list[str] = Field(min_length=1, max_length=5)


EXPLANATION_SYSTEM_PROMPT = """
You are RiskAssess, a financial-crime investigation support assistant. Create a
concise, neutral explanation using only the supplied alert context and factor
evidence. Do not claim criminality, invent facts, or recommend an automatic SAR,
payment block, account closure, or other adverse customer action. Return JSON
only with summary, key_drivers, mitigating_factors, recommended_checks, and
limitations. Explain why the alert deserves its queue priority, cite concrete
values in prose, identify missing data, and state that a human investigator is
accountable for disposition.
""".strip()


class RiskIntelligenceService:
    def __init__(
        self,
        settings: Settings,
        repository: RiskRepository,
        scoring: ScoringEngine,
        ai_core: AICoreClient,
        vector_store: HanaVectorStore,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.scoring = scoring
        self.ai_core = ai_core
        self.vector_store = vector_store

    def explain_alert(self, alert_id: str, refresh: bool = False) -> Explanation:
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)
        cached = self.repository.get_explanation(alert_id)
        if cached and not refresh:
            return cached.model_copy(update={"provenance": "cached"})

        score = self.scoring.score_alert(alert_id, refresh=refresh)
        citations = [evidence for factor in score.factors for evidence in factor.evidence]
        payload = {
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
            "company": context["company"],
            "score": score.model_dump(mode="json"),
            "retrieved_policy_context": self._retrieve_policy_context(context),
        }

        try:
            generated = ModelExplanation.model_validate(
                self.ai_core.chat_json(EXPLANATION_SYSTEM_PROMPT, payload)
            )
            provenance = "ai"
            model = self.settings.aicore_model_name
        except (AICoreError, ValidationError, ValueError, KeyError) as exc:
            logger.warning("AI explanation generation failed; using template fallback: %s", exc)
            generated = self._fallback_explanation(context, score.total, score.tier, score.factors)
            provenance = "fallback"
            model = "template-fallback-v1"

        result = Explanation(
            alert_id=alert_id,
            summary=generated.summary,
            key_drivers=generated.key_drivers,
            mitigating_factors=generated.mitigating_factors,
            recommended_checks=generated.recommended_checks,
            limitations=generated.limitations,
            citations=self._deduplicate_citations(citations),
            provenance=provenance,
            model=model,
            prompt_version=self.settings.prompt_version,
            generated_at=datetime.now(timezone.utc),
        )
        self.repository.save_explanation(result)
        return result

    def _retrieve_policy_context(self, context: dict) -> list[dict[str, str | float]]:
        query = " ".join(
            (
                str(context["alert_type"]),
                str(context["description"]),
                str(context["destination_country"]),
                str(context["company"]["risk_rating"]),
                "human accountability financial crime investigation",
            )
        )
        return self.vector_store.search(query, limit=3)

    @staticmethod
    def _fallback_explanation(context: dict, total: float, tier: str, factors: list) -> ModelExplanation:
        ranked = sorted(factors, key=lambda item: item.score / item.max_score, reverse=True)
        key_drivers = [
            f"{factor.label}: {factor.score:g}/{factor.max_score:g}. {factor.rationale}"
            for factor in ranked[:3]
        ]
        mitigations: list[str] = []
        company = context["company"]
        if not company["sanctions_match"]:
            mitigations.append("No sanctions match is present in the supplied entity profile.")
        if not company["pep"]:
            mitigations.append("No PEP flag is present in the supplied entity profile.")
        if not mitigations:
            mitigations.append("No material mitigating entity flags were present in the supplied data.")
        return ModelExplanation(
            summary=(
                f"This alert is prioritised as {tier.upper()} with a score of {total:g}/100. "
                f"The transfer of {context['currency']} {context['amount']:,.0f} from "
                f"{context['origin_country']} to {context['destination_country']} requires "
                "investigator review because the strongest supplied factors are "
                f"{ranked[0].label.lower()} and {ranked[1].label.lower()}."
            ),
            key_drivers=key_drivers,
            mitigating_factors=mitigations,
            recommended_checks=[
                "Verify the transaction purpose and supporting commercial documentation.",
                "Confirm the current beneficial owners and rerun sanctions/PEP screening.",
                "Review linked transfers and prior cases before recording a disposition.",
            ],
            limitations=[
                "This explanation uses only the data fields supplied to RiskAssess.",
                "The output is decision support; a human investigator remains accountable for disposition.",
            ],
        )

    @staticmethod
    def _deduplicate_citations(citations: list[EvidenceItem]) -> list[EvidenceItem]:
        seen: set[tuple[str, str, str]] = set()
        result: list[EvidenceItem] = []
        for citation in citations:
            key = (citation.label, citation.value, citation.source)
            if key not in seen:
                seen.add(key)
                result.append(citation)
        return result
