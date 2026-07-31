from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models.schemas import (
    ActionableInsight,
    EvidenceItem,
    InsightDecisionRecord,
    InsightDecisionRequest,
    ReasoningTraceItem,
    RecommendedAction,
    RiskScore,
    UrgencyComponent,
)
from app.services.ai_core_client import AICoreClient, AICoreError
from app.services.case_evidence import get_case_evidence
from app.services.presentable import (
    ACTION_LABELS,
    action_label,
    confidence_label,
    factor_label,
    tier_label,
    yes_no,
)
from app.services.privacy import redact_for_llm
from app.services.prompt_guard import injection_system_addendum
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)

PROMPT_VERSION = "insights-1.0"
DRAFT_DISCLAIMER = "Draft only — review and approve before submitting."

SYNTHESIS_SYSTEM_PROMPT = (
    """
You are RiskAssess workflow synthesis. The recommended_action, urgency_score, and
confidence are already decided by transparent rules and MUST NOT be changed.
Using only the supplied risk factors, evidence, and precedent context, return JSON
with: rationale (2-4 sentences in plain English citing factor display names such as
“Entity risk profile”, never snake_case keys),
draft_notes (internal case narrative draft in the voice of Amelia Reyes, Group Chief Risk Officer;
plain English only — no code identifiers, no key=value dumps, no JSON),
evidence_labels (short list of plain-English labels highlighting the strongest supporting data points).
Do not invent facts, claim criminality, or imply the recommendation has been executed.
Never recommend autonomous SAR filing, payment blocking, or alert closure.
""".strip()
    + "\n"
    + injection_system_addendum()
)


class ModelSynthesis(BaseModel):
    rationale: str = Field(min_length=20, max_length=1200)
    draft_notes: str = Field(min_length=20, max_length=2000)
    evidence_labels: list[str] = Field(default_factory=list, max_length=8)


class ActionableInsightsService:
    def __init__(
        self,
        settings: Settings,
        repository: RiskRepository,
        scoring: ScoringEngine,
        ai_core: AICoreClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.scoring = scoring
        self.ai_core = ai_core

    def get_insight(self, alert_id: str) -> ActionableInsight | None:
        return self.repository.get_insight(alert_id)

    def generate_insight(self, alert_id: str, refresh: bool = False) -> ActionableInsight:
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)

        fingerprint = ScoringEngine.source_fingerprint(context)
        cached = self.repository.get_insight(alert_id)
        if cached and cached.source_fingerprint == fingerprint and not refresh:
            return cached.model_copy(update={"status": cached.status})

        score = self.scoring.score_alert(alert_id, refresh=False, use_ai=False)
        case_data = self._case_evidence(alert_id, context)
        action, trace = self._recommend_action(context, score)
        urgency_score, urgency_breakdown = self._urgency_score(context, score)
        confidence = score.confidence.level
        confidence_reason = "; ".join(score.confidence.reasons) or (
            f"Overall confidence is {confidence_label(score.confidence.level)} based on key driving factor data quality."
        )

        # Low-confidence abstain: avoid forcing strong Clear/SAR when evidence is weak.
        if confidence == "low" and action in {"clear", "draft_sar"}:
            trace.append(
                ReasoningTraceItem(
                    rule_id="CONF-ABSTAIN-01",
                    matched=True,
                    inputs={"prior_action": action, "confidence": confidence},
                    note=(
                        "Low confidence steers the recommendation toward requesting additional KYC "
                        "rather than a strong Clear or Draft SAR path."
                    ),
                )
            )
            action = "request_kyc"

        evidence = self._assemble_evidence(context, score, case_data)
        synthesis = self._synthesize(context, score, action, urgency_score, confidence, evidence, case_data)

        # Prefer evidence ordered by labels the model highlighted, else keep assembled list.
        ordered_evidence = self._order_evidence(evidence, synthesis.get("evidence_labels", []))

        insight = ActionableInsight(
            insight_id=f"INS-{uuid.uuid4().hex[:10].upper()}",
            alert_id=alert_id,
            status="generated",
            recommended_action=action,  # type: ignore[arg-type]
            rationale=synthesis["rationale"],
            reasoning_trace=trace,
            urgency_score=urgency_score,
            urgency_breakdown=urgency_breakdown,
            evidence=ordered_evidence,
            precedent_cases=case_data["precedents"],
            draft_notes=synthesis["draft_notes"],
            draft_disclaimer=DRAFT_DISCLAIMER,
            draft_email=None,
            routing_suggestion=case_data["routing"],
            confidence=confidence,  # type: ignore[arg-type]
            confidence_reason=confidence_reason,
            provenance=synthesis["provenance"],  # type: ignore[arg-type]
            model=synthesis["model"],
            prompt_version=PROMPT_VERSION,
            generated_at=datetime.now(timezone.utc),
            source_fingerprint=fingerprint,
        )
        self.repository.save_insight(insight)
        return insight

    def apply_decision(self, alert_id: str, request: InsightDecisionRequest) -> tuple[ActionableInsight, InsightDecisionRecord]:
        insight = self.repository.get_insight(alert_id)
        if insight is None:
            raise KeyError(alert_id)
        if insight.status in {"approved", "overridden", "actioned", "further_info_requested"}:
            raise ValueError("Insight already decided; generate a refresh to create a new recommendation.")

        context = self.repository.get_alert_context(alert_id) or {}
        if request.decision == "approved":
            status_after = "approved"
        elif request.decision == "request_further_info":
            status_after = "further_info_requested"
        else:
            status_after = "overridden"

        updates: dict[str, Any] = {"status": status_after}
        if request.edited_draft_notes is not None:
            updates["draft_notes"] = request.edited_draft_notes
        email_body = request.edited_draft_email
        if email_body is None:
            email_body = self._build_csuite_email(context, insight, request.decision)
        updates["draft_email"] = email_body

        final = insight.model_copy(update=updates)
        self.repository.save_insight(final)

        record = InsightDecisionRecord(
            insight_id=insight.insight_id,
            alert_id=alert_id,
            decision=request.decision,
            reason_code=request.reason_code,
            free_text=request.free_text,
            edited_draft_notes=request.edited_draft_notes,
            actor=request.actor,
            decided_at=datetime.now(timezone.utc),
            previous_status="reviewed",
            resulting_status=status_after,  # type: ignore[arg-type]
        )
        self.repository.append_insight_decision(record)
        return final, record

    def update_draft_email(self, alert_id: str, draft_email: str) -> ActionableInsight:
        insight = self.repository.get_insight(alert_id)
        if insight is None:
            raise KeyError(alert_id)
        updated = insight.model_copy(update={"draft_email": draft_email})
        self.repository.save_insight(updated)
        return updated

    def build_csuite_email(self, alert_id: str, decision: str | None = None) -> str:
        insight = self.repository.get_insight(alert_id)
        if insight is None:
            raise KeyError(alert_id)
        context = self.repository.get_alert_context(alert_id) or {}
        return self._build_csuite_email(context, insight, decision or "approved")

    @staticmethod
    def _build_csuite_email(context: dict[str, Any], insight: ActionableInsight, decision: str) -> str:
        company = context.get("company") or {}
        company_name = context.get("company_name") or company.get("name") or "valued client"
        amount = context.get("amount")
        currency = context.get("currency") or ""
        action_labels = {
            "clear": "we are prepared to clear the monitoring alert following our review",
            "escalate_tier2": "we are escalating the matter to our Tier-2 financial crime unit for deeper review",
            "request_kyc": "we require additional KYC and supporting information to complete our review",
            "draft_sar": "we are progressing an internal suspicious activity assessment for further review",
        }
        decision_labels = {
            "approved": (
                "I have approved the recommended next step and am progressing the case on that basis"
            ),
            "overridden": (
                "I have declined the recommended next step and recorded an alternative disposition "
                "with documented rationale"
            ),
            "request_further_info": (
                "I am requesting further information from your organisation before we conclude the review"
            ),
        }
        decision_closings = {
            "approved": (
                "Please treat this correspondence as confidential and share only with colleagues "
                "who have a legitimate need to know."
            ),
            "overridden": (
                "Please treat this correspondence as confidential. Further internal coordination may "
                "follow as we execute the alternative path."
            ),
            "request_further_info": (
                "We would be grateful for your prompt cooperation in providing the requested "
                "clarification or documentation. Please treat this correspondence as confidential."
            ),
        }
        recommended = action_labels.get(insight.recommended_action, "we are continuing our review with appropriate oversight")
        decision_line = decision_labels.get(decision, "I am progressing the case with appropriate oversight")
        closing = decision_closings.get(
            decision,
            "Please treat this correspondence as confidential and share only with colleagues who have a legitimate need to know.",
        )
        amount_text = f"{currency} {amount:,.0f}" if isinstance(amount, (int, float)) else "the referenced transfer"

        return (
            f"Subject: Confidential compliance review update — {company_name} ({insight.alert_id})\n\n"
            f"Dear Members of the Executive Leadership Team,\n\n"
            f"I am writing as Group Chief Risk Officer of TrustSphere Bank regarding a "
            f"transaction-monitoring alert linked to {company_name} ({insight.alert_id}). "
            f"This correspondence is informational and does not itself constitute a regulatory filing, "
            f"payment block, or final adverse finding.\n\n"
            f"Case summary\n"
            f"• Alert: {context.get('alert_type', 'Monitoring alert')}\n"
            f"• Transaction: {amount_text} from {context.get('origin_country', 'N/A')} "
            f"to {context.get('destination_country', 'N/A')}\n"
            f"• Risk priority: {insight.urgency_score:.0f}/100 urgency exposure "
            f"(distinct from the underlying risk score); recommendation confidence: "
            f"{confidence_label(insight.confidence)}.\n"
            f"• Recommended path: {recommended}.\n\n"
            f"Decision status\n"
            f"{decision_line.capitalize()}. "
            f"No automated disposition has been taken.\n\n"
            f"Rationale\n"
            f"{insight.rationale}\n\n"
            f"{closing}\n\n"
            f"Respectfully,\n"
            f"Amelia Reyes\n"
            f"Group Chief Risk Officer\n"
            f"TrustSphere Bank"
        )

    def _case_evidence(self, alert_id: str, context: dict[str, Any]) -> dict[str, Any]:
        return get_case_evidence(alert_id, context)

    def _factor_map(self, score: RiskScore) -> dict[str, float]:
        return {factor.key: factor.score for factor in score.factors}

    def _recommend_action(
        self, context: dict[str, Any], score: RiskScore
    ) -> tuple[RecommendedAction, list[ReasoningTraceItem]]:
        company = context["company"]
        signals = context.get("signals", {})
        factors = self._factor_map(score)
        entity = factors.get("entity_risk", 0.0)
        geographic = factors.get("geographic_risk", 0.0)
        regulatory = factors.get("regulatory_sensitivity", 0.0)
        amount_ratio = float(signals.get("amount_ratio") or context.get("amount_ratio") or 1.0)
        layers = int(company.get("beneficial_owner_layers") or 0)
        prior_cases = int(company.get("prior_cases") or 0)
        sanctions = bool(company.get("sanctions_match"))
        pep = bool(company.get("pep"))
        new_corridor = bool(signals.get("new_corridor"))
        alert_type = str(context.get("alert_type") or "")
        fatf = str(signals.get("fatf_risk") or "Unknown")
        incomplete = fatf.lower() == "unknown" or not context.get("transaction")

        trace: list[ReasoningTraceItem] = []

        sar_inputs = {
            "sanctions_match": sanctions,
            "tier": score.tier,
            "entity_risk": entity,
            "prior_cases": prior_cases,
        }
        sar_match = sanctions or (score.tier == "high" and entity >= 18 and prior_cases >= 2)
        trace.append(
            ReasoningTraceItem(
                rule_id="SAR-01",
                matched=sar_match,
                inputs=sar_inputs,
                note="Draft SAR when sanctions hit, or high tier with elevated entity risk and prior cases.",
            )
        )
        if sar_match:
            return "draft_sar", trace

        escalate_inputs = {
            "tier": score.tier,
            "pep": pep,
            "geographic_risk": geographic,
            "regulatory_sensitivity": regulatory,
            "alert_type": alert_type,
        }
        escalate_match = score.tier == "high" or (
            score.tier == "medium"
            and (
                pep
                or geographic >= 14
                or regulatory >= 10
                or "structur" in alert_type.lower()
            )
        )
        trace.append(
            ReasoningTraceItem(
                rule_id="ESC-01",
                matched=escalate_match,
                inputs=escalate_inputs,
                note="Escalate to Tier 2 for high priority, or medium priority with PEP, geographic, regulatory, or structuring signals.",
            )
        )
        if escalate_match:
            return "escalate_tier2", trace

        kyc_inputs = {
            "incomplete_evidence": incomplete,
            "beneficial_owner_layers": layers,
            "tier": score.tier,
            "amount_ratio": amount_ratio,
            "new_corridor": new_corridor,
        }
        kyc_match = (
            incomplete
            or layers >= 3
            or (score.tier == "medium" and (amount_ratio >= 2.0 or new_corridor))
        )
        trace.append(
            ReasoningTraceItem(
                rule_id="KYC-01",
                matched=kyc_match,
                inputs=kyc_inputs,
                note="Request additional KYC when evidence is weak, ownership is layered, or medium-priority deviation exists.",
            )
        )
        if kyc_match:
            return "request_kyc", trace

        clear_inputs = {
            "tier": score.tier,
            "sanctions_match": sanctions,
            "pep": pep,
            "amount_ratio": amount_ratio,
            "prior_cases": prior_cases,
        }
        clear_match = (
            score.tier == "low"
            and not sanctions
            and not pep
            and amount_ratio < 2.0
            and prior_cases == 0
        )
        trace.append(
            ReasoningTraceItem(
                rule_id="CLR-01",
                matched=clear_match,
                inputs=clear_inputs,
                note="Clear only for low-priority alerts without sanctions or PEP exposure, modest amount deviation, and no prior cases.",
            )
        )
        if clear_match:
            return "clear", trace

        # Safe default when no rule fully matches.
        trace.append(
            ReasoningTraceItem(
                rule_id="KYC-DEFAULT",
                matched=True,
                inputs={"tier": score.tier},
                note="No strong Clear, Escalate, or SAR match; default to request additional KYC information.",
            )
        )
        return "request_kyc", trace

    def _urgency_score(
        self, context: dict[str, Any], score: RiskScore
    ) -> tuple[float, list[UrgencyComponent]]:
        created = context.get("created_at")
        now = datetime.now(timezone.utc)
        if isinstance(created, datetime):
            created_aware = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            hours_open = max(0.0, (now - created_aware).total_seconds() / 3600.0)
        else:
            hours_open = 0.0

        sla_points = min(35.0, (hours_open / 24.0) * 7.0)
        tier_weight = {"high": 25.0, "medium": 12.0, "low": 4.0}.get(score.tier, 4.0)
        factors = self._factor_map(score)
        regulatory = factors.get("regulatory_sensitivity", 0.0)
        # Scale 0–15 factor points into 0–20 urgency contribution.
        regulatory_points = min(20.0, regulatory * (20.0 / 15.0))
        sanctions_points = 15.0 if context["company"].get("sanctions_match") else 0.0
        amount = float(context.get("amount") or 0.0)
        amount_points = min(10.0, math.log10(max(amount, 1.0)) * 1.6)

        breakdown = [
            UrgencyComponent(
                component="sla_ageing",
                points=round(sla_points, 1),
                detail=f"{hours_open:.1f} hours unresolved (exposure grows while open).",
            ),
            UrgencyComponent(
                component="tier_weight",
                points=round(tier_weight, 1),
                detail=f"Risk tier {score.tier} contributes fixed exposure weight.",
            ),
            UrgencyComponent(
                component="regulatory_sensitivity",
                points=round(regulatory_points, 1),
                detail=f"Regulatory sensitivity factor {regulatory:.1f}/15 scaled to urgency.",
            ),
            UrgencyComponent(
                component="sanctions_exposure",
                points=round(sanctions_points, 1),
                detail="Sanctions match adds fixed regulatory exposure while unresolved."
                if sanctions_points
                else "No sanctions match.",
            ),
            UrgencyComponent(
                component="amount_exposure",
                points=round(amount_points, 1),
                detail=f"Log-scaled amount exposure for {amount:,.0f} {context.get('currency', '')}.",
            ),
        ]
        total = round(min(100.0, sum(item.points for item in breakdown)), 1)
        return total, breakdown

    def _confidence(self, context: dict[str, Any], score: RiskScore) -> tuple[str, str]:
        """Deprecated: confidence now comes from score.confidence rollup."""
        return score.confidence.level, "; ".join(score.confidence.reasons)

    def _assemble_evidence(
        self, context: dict[str, Any], score: RiskScore, case_data: dict[str, Any]
    ) -> list[EvidenceItem]:
        company = context["company"]
        signals = context.get("signals", {})
        items: list[EvidenceItem] = [
            EvidenceItem(
                label="Risk score total",
                value=f"{score.total} ({tier_label(score.tier)} priority)",
                source="RiskAssess scoring",
            ),
            EvidenceItem(
                label="Sanctions / PEP",
                value=(
                    f"Sanctions match: {yes_no(company.get('sanctions_match'))}; "
                    f"PEP association: {yes_no(company.get('pep'))}"
                ),
                source="Company screening",
            ),
            EvidenceItem(
                label="Amount versus baseline",
                value=f"{float(signals.get('amount_ratio') or context.get('amount_ratio') or 1):.1f}× baseline",
                source="Transaction baselines",
            ),
            EvidenceItem(
                label="Prior compliance cases",
                value=str(company.get("prior_cases")),
                source="Compliance case history",
            ),
            EvidenceItem(
                label="Counterparty history",
                value=str(case_data.get("counterparty_history")),
                source="Case evidence store",
            ),
            EvidenceItem(
                label="Transaction details",
                value=str(case_data.get("transaction_metadata")),
                source="Case evidence store",
            ),
        ]
        for factor in score.factors:
            if factor.score >= factor.max_score * 0.6:
                items.append(
                    EvidenceItem(
                        label=f"Elevated factor: {factor.label or factor_label(factor.key)}",
                        value=f"{factor.score}/{factor.max_score} — {factor.rationale}",
                        source="Risk factor evidence",
                    )
                )
        return items

    def _synthesize(
        self,
        context: dict[str, Any],
        score: RiskScore,
        action: str,
        urgency_score: float,
        confidence: str,
        evidence: list[EvidenceItem],
        case_data: dict[str, Any],
    ) -> dict[str, Any]:
        payload = redact_for_llm(
            {
                "locked_recommendation": {
                    "recommended_action": action,
                    "action_label": ACTION_LABELS[action],
                    "urgency_score": urgency_score,
                    "confidence": confidence,
                },
                "alert": {
                    "id": context["id"],
                    "type": context["alert_type"],
                    "description": context["description"],
                },
                "company_name": context.get("company_name"),
                "score": score.model_dump(mode="json"),
                "evidence": [item.model_dump() for item in evidence],
                "precedent_cases": [item.model_dump() for item in case_data["precedents"]],
                "instruction": "Do not change recommended_action, urgency_score, or confidence.",
            }
        )
        try:
            generated = ModelSynthesis.model_validate(
                self.ai_core.chat_json(SYNTHESIS_SYSTEM_PROMPT, payload)
            )
            return {
                "rationale": generated.rationale,
                "draft_notes": generated.draft_notes,
                "evidence_labels": generated.evidence_labels,
                "provenance": "rules+ai",
                "model": self.settings.aicore_model_name,
            }
        except (AICoreError, ValidationError, ValueError, KeyError) as exc:
            logger.warning("Insight synthesis failed; using template fallback: %s", exc)
            return self._fallback_synthesis(context, score, action, urgency_score, confidence)

    def _fallback_synthesis(
        self,
        context: dict[str, Any],
        score: RiskScore,
        action: str,
        urgency_score: float,
        confidence: str,
    ) -> dict[str, Any]:
        top = sorted(score.factors, key=lambda item: item.score / item.max_score, reverse=True)[:3]
        cited = ", ".join(
            f"{item.label or factor_label(item.key)} ({item.score}/{item.max_score})" for item in top
        )
        label = action_label(action)
        rationale = (
            f"The structured review recommends “{label}” for alert {context['id']} "
            f"({tier_label(score.tier)} priority, score {score.total}). "
            f"Primary drivers: {cited}. "
            f"Urgency/exposure is {urgency_score}/100 (distinct from the risk score). "
            f"Confidence is {confidence_label(confidence)}."
        )
        draft_notes = (
            f"Draft case note — review before submitting.\n"
            f"Alert {context['id']} ({context['alert_type']}) for {context['company_name']}.\n"
            f"Recommended next step: {label}. Risk score {score.total} "
            f"({tier_label(score.tier)} priority); urgency/exposure {urgency_score}.\n"
            f"Key factors: {cited}.\n"
            f"Entity screening: sanctions match {yes_no(context['company'].get('sanctions_match'))}; "
            f"PEP association {yes_no(context['company'].get('pep'))}; "
            f"prior compliance cases {context['company'].get('prior_cases')}.\n"
            f"Prepared for Group Chief Risk Officer review. This note must be reviewed before any disposition is recorded. "
            f"No payment block, SAR filing, or alert closure has been performed."
        )
        return {
            "rationale": rationale,
            "draft_notes": draft_notes,
            "evidence_labels": [item.label or factor_label(item.key) for item in top],
            "provenance": "rules+fallback",
            "model": "deterministic-synthesis-v1",
        }

    @staticmethod
    def _order_evidence(evidence: list[EvidenceItem], labels: list[str]) -> list[EvidenceItem]:
        if not labels:
            return evidence
        lowered = [label.lower() for label in labels]
        prioritized: list[EvidenceItem] = []
        remainder: list[EvidenceItem] = []
        for item in evidence:
            haystack = f"{item.label} {item.value}".lower()
            if any(label in haystack for label in lowered):
                prioritized.append(item)
            else:
                remainder.append(item)
        return prioritized + remainder
