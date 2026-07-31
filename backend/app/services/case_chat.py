from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models.schemas import (
    ChatAuditRecord,
    ChatChartSeries,
    ChatChartSpec,
    ChatCitation,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSuggestion,
    ChatThreadResponse,
    RiskScore,
)
from app.services.ai_core_client import AICoreClient, AICoreError
from app.services.case_evidence import get_case_evidence
from app.services.privacy import redact_for_llm
from app.services.prompt_guard import (
    detects_disallowed_action,
    injection_system_addendum,
    sanitize_user_message,
    wrap_untrusted,
)
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore

logger = logging.getLogger(__name__)

PROMPT_VERSION = "casechat-1.0"
ACTOR = "Amelia Reyes, Group Chief Risk Officer"

CHAT_SYSTEM_PROMPT = (
    """
You are RiskAssess Case Assistant for a single financial-crime alert. The user is
Amelia Reyes, Group Chief Risk Officer. Answer ONLY using the supplied grounding pack
(score factors, evidence, case data, policy passages, optional chart summary). Return JSON with:
reply (plain English for the Group Chief Risk Officer — never snake_case keys, never key=value dumps, never JSON),
citations (array of {label, value, source, kind} where kind is one of
factor|evidence|precedent|policy|case_field|chart; labels and sources must be plain English),
suggested_draft_snippet (string or null — only when the user asked to draft/refine notes;
write in the voice of the Group Chief Risk Officer for internal case notes in plain English),
suggested_email_draft (string or null — only when the user asked to draft a client/c-suite email;
must be a complete, send-ready email with Subject line based on the user's instructions and case facts;
sign as Amelia Reyes, Group Chief Risk Officer; do not label it as a draft or say it was not sent),
refused_action (boolean),
refusal_reason (string or null).
Never invent facts. If data is missing, say so. Never clear, escalate, file a SAR,
or block a payment — if asked, set refused_action true and point the Group Chief Risk Officer
to Approve/Override on the Actionable Insights card. Do not change risk scores.
When the user asks to show, compare, visualise, plot, chart, or see trends/history/breakdowns,
a chart may be attached; still explain the chart in reply using plain English factor names.
""".strip()
    + "\n"
    + injection_system_addendum()
)


class ModelChatReply(BaseModel):
    reply: str = Field(min_length=10, max_length=2500)
    citations: list[dict[str, str]] = Field(default_factory=list)
    suggested_draft_snippet: str | None = None
    suggested_email_draft: str | None = None
    refused_action: bool = False
    refusal_reason: str | None = None


class CaseChatService:
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

    def get_thread(self, alert_id: str) -> ChatThreadResponse:
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)
        score = self.scoring.score_alert(alert_id, refresh=False, use_ai=False)
        activity = self.repository.get_transaction_activity(str(context["company_id"]), score.total)
        return ChatThreadResponse(
            alert_id=alert_id,
            messages=self.repository.get_chat_thread(alert_id),
            suggestions=self.build_suggestions(alert_id, context, score, activity),
            greeting=self._greeting(alert_id),
        )

    def chat(self, alert_id: str, request: ChatRequest) -> ChatResponse:
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)

        message = sanitize_user_message(request.message)
        score = self.scoring.score_alert(alert_id, refresh=False, use_ai=False)
        activity = self.repository.get_transaction_activity(str(context["company_id"]), score.total)
        case_data = get_case_evidence(alert_id, context)
        explanation = self.repository.get_explanation(alert_id)
        insight = self.repository.get_insight(alert_id)
        policy_hits = self.vector_store.search(f"{message} {context.get('alert_type', '')}", limit=3)

        refused = detects_disallowed_action(message)
        chart_type = self._detect_chart_type(message)
        chart = self._build_chart(chart_type, context, score, activity, case_data) if chart_type else None

        grounding = redact_for_llm(
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
                "signals": context.get("signals", {}),
                "score": score.model_dump(mode="json"),
                "activity_summary": [
                    {
                        "period": p.get("period"),
                        "total_amount": p.get("total_amount"),
                        "transaction_count": p.get("transaction_count"),
                    }
                    for p in activity
                ],
                "case_evidence": {
                    "counterparty_history": case_data.get("counterparty_history"),
                    "prior_alerts": case_data.get("prior_alerts"),
                    "transaction_metadata": case_data.get("transaction_metadata"),
                    "sanctions_list_version": case_data.get("sanctions_list_version"),
                    "related_transactions": case_data.get("related_transactions"),
                    "prior_alert_summaries": case_data.get("prior_alert_summaries"),
                    "precedents": [
                        p.model_dump() if hasattr(p, "model_dump") else p
                        for p in case_data.get("precedents", [])
                    ],
                    "precedent_cases_detail": case_data.get("precedent_cases_detail"),
                },
                "explanation": explanation.model_dump(mode="json") if explanation else None,
                "insight": insight.model_dump(mode="json") if insight else None,
                "policy_passages": [
                    {
                        **hit,
                        "content": wrap_untrusted("policy", str(hit.get("content") or "")),
                    }
                    for hit in policy_hits
                ],
                "chart": chart.model_dump(mode="json") if chart else None,
                "action_request_detected": refused,
                "history": [m.model_dump(mode="json") for m in self.repository.get_chat_thread(alert_id)[-12:]],
                "user_message_plain": message,
                "user_message": wrap_untrusted("user_message", message),
            }
        )

        if refused:
            synthesis = {
                "reply": (
                    "I can’t clear, escalate, file a SAR, or block a payment. "
                    "Use Approve, Override, or Prompt entity for further questioning on the "
                    "Actionable Insights recommendation card so the disposition stays human-clicked and auditable."
                ),
                "citations": [],
                "suggested_draft_snippet": None,
                "suggested_email_draft": None,
                "refused_action": True,
                "refusal_reason": "Action requests are blocked; disposition must use Approve/Override controls.",
                "provenance": "fallback",
                "model": "guardrail-v1",
            }
        else:
            synthesis = self._synthesize(grounding)
            if self._wants_email(message) and not synthesis.get("suggested_email_draft"):
                synthesis["suggested_email_draft"] = self._fallback_email(context, insight, message)
                if "email" not in str(synthesis.get("reply", "")).lower():
                    synthesis["reply"] = (
                        str(synthesis.get("reply") or "")
                        + " I’ve prepared a send-ready email you can insert into the Draft Email module."
                    ).strip()

        citations = self._normalize_citations(synthesis.get("citations") or [], score, case_data, policy_hits, chart)
        if chart and not any(c.kind == "chart" for c in citations):
            citations.append(
                ChatCitation(
                    label=chart.citation_label,
                    value=chart.title,
                    source=chart.source,
                    kind="chart",
                )
            )
        # Prefer a clean evidence list under charts: include factor/case citations after the chart citation.
        if chart:
            citations = self._chart_evidence_list(citations, score, case_data, activity)

        turn_id = f"TURN-{uuid.uuid4().hex[:10].upper()}"
        thread_id = f"THREAD-{alert_id}"
        now = datetime.now(timezone.utc)
        reply = str(synthesis["reply"])
        draft_snippet = synthesis.get("suggested_draft_snippet")
        email_draft = synthesis.get("suggested_email_draft")
        refused_action = bool(synthesis.get("refused_action") or refused)
        refusal_reason = synthesis.get("refusal_reason") if refused_action else None

        if isinstance(email_draft, str) and email_draft.strip() and insight is not None:
            self.repository.save_insight(insight.model_copy(update={"draft_email": email_draft}))

        user_msg = ChatMessage(role="user", content=message, created_at=now)
        assistant_msg = ChatMessage(
            role="assistant",
            content=reply,
            citations=citations,
            chart=chart,
            created_at=now,
        )
        self.repository.append_chat_messages(alert_id, [user_msg, assistant_msg])
        self.repository.append_chat_audit(
            ChatAuditRecord(
                turn_id=turn_id,
                alert_id=alert_id,
                user_message=message,
                assistant_reply=reply,
                citations=citations,
                chart_type=chart.chart_type if chart else None,
                refused_action=refused_action,
                actor=ACTOR,
                created_at=now,
            )
        )

        return ChatResponse(
            alert_id=alert_id,
            reply=reply,
            citations=citations,
            chart=chart,
            suggested_draft_snippet=draft_snippet if isinstance(draft_snippet, str) else None,
            suggested_email_draft=email_draft if isinstance(email_draft, str) else None,
            refused_action=refused_action,
            refusal_reason=refusal_reason,
            provenance=synthesis["provenance"],  # type: ignore[arg-type]
            model=str(synthesis["model"]),
            prompt_version=PROMPT_VERSION,
            turn_id=turn_id,
            thread_id=thread_id,
        )

    def build_suggestions(
        self,
        alert_id: str,
        context: dict[str, Any],
        score: RiskScore,
        activity: list[dict],
    ) -> list[ChatSuggestion]:
        top = max(score.factors, key=lambda f: f.score / f.max_score if f.max_score else 0)
        why = ChatSuggestion(
            id="why_factor",
            label=f"Why is {top.label.lower()} {top.score:.0f}/{top.max_score:.0f}?",
            prompt=(
                f"Why is {top.label} scored {top.score}/{top.max_score} "
                f"for this transaction? Cite the factor evidence and confidence in plain English."
            ),
        )
        if activity:
            second = ChatSuggestion(
                id="chart_activity",
                label="Chart activity vs baseline",
                prompt="Chart this entity's recent transaction activity against its baseline.",
            )
        else:
            second = ChatSuggestion(
                id="precedent",
                label="Have we seen this pattern?",
                prompt="Have we seen this pattern before? Show a similar past case and outcome.",
            )
        insight = self.repository.get_insight(alert_id)
        if insight:
            third = ChatSuggestion(
                id="draft_notes",
                label="Refine my case notes",
                prompt="Help refine my case notes using this case's evidence, written for the Group Chief Risk Officer.",
            )
        else:
            company = context["company"]
            third = ChatSuggestion(
                id="policy_sla",
                label="What policy/SLA applies?",
                prompt=(
                    "What policy or SLA applies given "
                    f"PEP association {'present' if company.get('pep') else 'not present'}, "
                    f"sanctions match {'yes' if company.get('sanctions_match') else 'no'}, "
                    f"and destination country risk "
                    f"{context.get('signals', {}).get('fatf_risk', 'unknown')} on this alert?"
                ),
            )
        return [why, second, third]

    @staticmethod
    def _greeting(alert_id: str) -> str:
        return (
            f"Hi Amelia — I’m your case assistant for {alert_id}. "
            "I support you as Group Chief Risk Officer and can only reason over this transaction’s "
            "evidence, risk factors, precedent, and policy. Ask a question or pick a suggestion below."
        )

    @staticmethod
    def _detect_chart_type(message: str) -> str | None:
        lower = message.lower()
        factor_intent = any(
            token in lower
            for token in (
                "factor breakdown",
                "risk factor",
                "factor score",
                "which factors",
                "score breakdown",
                "breakdown of risk",
                "breakdown of the risk",
            )
        )
        precedent_intent = any(
            token in lower
            for token in (
                "precedent",
                "similar case",
                "similar pattern",
                "past case",
                "historical outcome",
                "outcome mix",
            )
        )
        activity_intent = any(
            token in lower
            for token in (
                "activity",
                "baseline",
                "over time",
                "trend",
                "monthly",
                "volume",
                "history",
                "historical",
                "transaction count",
                "amount over",
                "vs baseline",
                "versus baseline",
                "compared to baseline",
                "compare to baseline",
            )
        )
        visual_intent = any(
            token in lower
            for token in (
                "chart",
                "graph",
                "plot",
                "visuali",
                "show me",
                "display",
                "draw",
                "illustrate",
            )
        )

        if factor_intent and (visual_intent or "breakdown" in lower or "show" in lower):
            return "factor_breakdown"
        if precedent_intent and (visual_intent or "outcome" in lower or "show" in lower or "how many" in lower):
            return "precedent_outcomes"
        if activity_intent and (visual_intent or "how" in lower or "what" in lower or "compare" in lower):
            return "activity_vs_baseline"
        if visual_intent:
            if "factor" in lower:
                return "factor_breakdown"
            if "precedent" in lower or "outcome" in lower:
                return "precedent_outcomes"
            return "activity_vs_baseline"
        # Implicit chart needs without explicit "chart/graph" wording
        if activity_intent:
            return "activity_vs_baseline"
        if factor_intent:
            return "factor_breakdown"
        if precedent_intent and ("how often" in lower or "how many" in lower or "distribution" in lower):
            return "precedent_outcomes"
        return None

    def _build_chart(
        self,
        chart_type: str,
        context: dict[str, Any],
        score: RiskScore,
        activity: list[dict],
        case_data: dict[str, Any],
    ) -> ChatChartSpec | None:
        if chart_type == "activity_vs_baseline":
            if not activity:
                return None
            baseline = float(context["company"].get("baseline_average_amount") or 0)
            points = [
                {
                    "period": str(row.get("period")),
                    "total_amount": float(row.get("total_amount") or 0),
                    "transaction_count": int(row.get("transaction_count") or 0),
                    "baseline": baseline,
                }
                for row in activity
            ]
            return ChatChartSpec(
                chart_type="activity_vs_baseline",
                title="Transaction activity vs baseline",
                x_key="period",
                series=[
                    ChatChartSeries(key="total_amount", label="Total amount", type="bar"),
                    ChatChartSeries(key="baseline", label="Baseline average", type="line"),
                ],
                points=points,
                baseline=baseline,
                currency=str(context.get("currency") or ""),
                source="Transaction activity and baselines",
                citation_label="Entity activity series",
            )
        if chart_type == "factor_breakdown":
            points = [
                {
                    "factor": factor.label,
                    "score": factor.score,
                    "max_score": factor.max_score,
                }
                for factor in score.factors
            ]
            return ChatChartSpec(
                chart_type="factor_breakdown",
                title="Risk factor breakdown",
                x_key="factor",
                series=[ChatChartSeries(key="score", label="Factor score", type="bar")],
                points=points,
                source="RiskAssess scoring engine",
                citation_label="Five-factor risk score",
            )
        if chart_type == "precedent_outcomes":
            details = case_data.get("precedent_cases_detail") or []
            counts: dict[str, int] = {}
            from app.services.presentable import action_label

            for item in details:
                raw = str(item.get("outcome") or item.get("disposition") or "Unknown")
                key = action_label(raw) if raw in {
                    "clear", "escalate_tier2", "request_kyc", "draft_sar"
                } else raw
                counts[key] = counts.get(key, 0) + 1
            if not counts:
                for prec in case_data.get("precedents") or []:
                    data = prec.model_dump() if hasattr(prec, "model_dump") else prec
                    label = str(data.get("typical_outcome") or "Typical outcome")[:40]
                    counts[label] = int(data.get("similar_count") or 1)
            if not counts:
                return None
            points = [{"outcome": key, "count": value} for key, value in counts.items()]
            return ChatChartSpec(
                chart_type="precedent_outcomes",
                title="Precedent outcome mix",
                x_key="outcome",
                series=[ChatChartSeries(key="count", label="Cases", type="bar")],
                points=points,
                source="Precedent case evidence",
                citation_label="Precedent outcomes",
            )
        return None

    def _synthesize(self, grounding: dict[str, Any]) -> dict[str, Any]:
        try:
            generated = ModelChatReply.model_validate(
                self.ai_core.chat_json(CHAT_SYSTEM_PROMPT, grounding)
            )
            return {
                "reply": generated.reply,
                "citations": generated.citations,
                "suggested_draft_snippet": generated.suggested_draft_snippet,
                "suggested_email_draft": generated.suggested_email_draft,
                "refused_action": generated.refused_action,
                "refusal_reason": generated.refusal_reason,
                "provenance": "ai",
                "model": self.settings.aicore_model_name,
            }
        except (AICoreError, ValidationError, ValueError, KeyError) as exc:
            logger.warning("Case chat synthesis failed; using fallback: %s", exc)
            return self._fallback_reply(grounding)

    def _fallback_reply(self, grounding: dict[str, Any]) -> dict[str, Any]:
        message = str(grounding.get("user_message_plain") or grounding.get("user_message") or "").lower()
        if "begin_untrusted" in message:
            # Prefer plain text when only the delimited form is present.
            start = message.find("]\n")
            end = message.find("\nend_untrusted")
            if start != -1 and end != -1 and end > start:
                message = message[start + 2 : end].strip()
        score = grounding.get("score") or {}
        factors = score.get("factors") or []
        chart = grounding.get("chart")
        case = grounding.get("case_evidence") or {}
        policy = grounding.get("policy_passages") or []
        citations: list[dict[str, str]] = []

        if chart:
            reply = (
                f"Here is a grounded chart for this case: {chart.get('title')}. "
                f"Data source: {chart.get('source')}. "
                "Series are taken from case history — no points were invented."
            )
            citations.append(
                {
                    "label": str(chart.get("citation_label") or "Chart"),
                    "value": str(chart.get("title")),
                    "source": str(chart.get("source")),
                    "kind": "chart",
                }
            )
        elif "precedent" in message or "pattern before" in message:
            details = case.get("precedent_cases_detail") or []
            if details:
                sample = details[0]
                reply = (
                    f"Similar pattern: {sample.get('pattern')} ({sample.get('case_id')}, {sample.get('year')}). "
                    f"Outcome: {sample.get('outcome')}. Notes: {sample.get('notes')}"
                )
                citations.append(
                    {
                        "label": str(sample.get("case_id")),
                        "value": str(sample.get("outcome")),
                        "source": "Mock precedent case detail",
                        "kind": "precedent",
                    }
                )
            else:
                reply = "No drillable precedent cases are available for this alert in the case store."
        elif "policy" in message or "sla" in message:
            if policy:
                doc = policy[0]
                reply = f"From {doc.get('title')}: {doc.get('content')}"
                citations.append(
                    {
                        "label": str(doc.get("title")),
                        "value": str(doc.get("content"))[:240],
                        "source": str(doc.get("source") or "policy"),
                        "kind": "policy",
                    }
                )
            else:
                reply = "No matching policy passage was retrieved for this question."
        elif self._wants_email(message):
            email = self._fallback_email(
                {
                    "id": grounding["alert"]["id"],
                    "company_name": (grounding.get("company") or {}).get("name"),
                    "alert_type": grounding["alert"]["type"],
                    "amount": (grounding.get("transaction") or {}).get("amount"),
                    "currency": (grounding.get("transaction") or {}).get("currency"),
                    "origin_country": (grounding.get("transaction") or {}).get("origin_country"),
                    "destination_country": (grounding.get("transaction") or {}).get("destination_country"),
                    "company": grounding.get("company") or {},
                },
                None,
                str(grounding.get("user_message_plain") or grounding.get("user_message") or ""),
            )
            return {
                "reply": "I’ve prepared a send-ready email from your instructions and the case facts. You can insert it into the Draft Email module.",
                "citations": [
                    {
                        "label": "Alert",
                        "value": grounding["alert"]["id"],
                        "source": "Case grounding",
                        "kind": "case_field",
                    }
                ],
                "suggested_draft_snippet": None,
                "suggested_email_draft": email,
                "refused_action": False,
                "refusal_reason": None,
                "provenance": "fallback",
                "model": "deterministic-chat-fallback-v1",
            }
        elif "draft" in message:
            top = sorted(factors, key=lambda f: float(f.get("score") or 0), reverse=True)[:2]
            cited = ", ".join(
                f"{f.get('label') or f.get('key')} ({f.get('score')}/{f.get('max_score')})"
                for f in top
            ) or "available factors"
            snippet = (
                f"Draft case note — review before submitting.\n"
                f"Alert {grounding['alert']['id']}: reviewed factors {cited}. "
                f"Counterparty history: {case.get('counterparty_history')}. "
                "Prepared for Group Chief Risk Officer review. No disposition has been submitted from chat."
            )
            reply = "Here is a case-note snippet you can insert into Actionable Insights for review."
            return {
                "reply": reply,
                "citations": [
                    {
                        "label": "Counterparty history",
                        "value": str(case.get("counterparty_history")),
                        "source": "Mock case-data store",
                        "kind": "case_field",
                    }
                ],
                "suggested_draft_snippet": snippet,
                "suggested_email_draft": None,
                "refused_action": False,
                "refusal_reason": None,
                "provenance": "fallback",
                "model": "deterministic-chat-fallback-v1",
            }
        else:
            if factors:
                top = max(factors, key=lambda f: float(f.get("score") or 0) / max(float(f.get("max_score") or 1), 1))
                reply = (
                    f"{top.get('label')} is scored {top.get('score')}/{top.get('max_score')}. "
                    f"Rationale: {top.get('rationale')} "
                    f"Overall confidence: {(score.get('confidence') or {}).get('level', 'unknown')}."
                )
                citations.append(
                    {
                        "label": str(top.get("label") or top.get("key")),
                        "value": f"{top.get('score')}/{top.get('max_score')}",
                        "source": "Risk factor evidence",
                        "kind": "factor",
                    }
                )
            else:
                reply = "Insufficient scored factors are available to answer that question for this alert."

        return {
            "reply": reply,
            "citations": citations,
            "suggested_draft_snippet": None,
            "suggested_email_draft": None,
            "refused_action": False,
            "refusal_reason": None,
            "provenance": "fallback",
            "model": "deterministic-chat-fallback-v1",
        }

    @staticmethod
    def _wants_email(message: str) -> bool:
        lower = message.lower()
        return any(
            token in lower
            for token in (
                "draft an email",
                "draft email",
                "write an email",
                "compose an email",
                "email to the",
                "c-suite",
                "csuite",
                "email the client",
                "client email",
            )
        )

    @staticmethod
    def _fallback_email(context: dict[str, Any], insight: Any, user_message: str) -> str:
        company = context.get("company") or {}
        company_name = context.get("company_name") or company.get("name") or "valued client"
        amount = context.get("amount")
        currency = context.get("currency") or ""
        amount_text = f"{currency} {amount:,.0f}" if isinstance(amount, (int, float)) else "the referenced transfer"
        from app.services.presentable import action_label

        decision = (
            action_label(insight.recommended_action)
            if insight is not None
            else "continued review"
        )
        return (
            f"Subject: Confidential compliance correspondence — {company_name}\n\n"
            f"Dear Members of the Executive Leadership Team,\n\n"
            f"I am writing as Group Chief Risk Officer of TrustSphere Bank regarding alert "
            f"{context.get('id', 'N/A')} for {company_name}. "
            f"This note responds to the following request: “{user_message.strip()}”.\n\n"
            f"We are reviewing {amount_text} "
            f"({context.get('origin_country', 'N/A')} → {context.get('destination_country', 'N/A')}) "
            f"under alert type “{context.get('alert_type', 'monitoring alert')}”. "
            f"Current recommended path: {decision}. "
            f"No payment has been blocked and no SAR has been filed as a result of this correspondence.\n\n"
            f"We would appreciate any clarification your team can provide and will keep you informed. "
            f"Please treat this correspondence as confidential.\n\n"
            f"Respectfully,\n"
            f"Amelia Reyes\n"
            f"Group Chief Risk Officer\n"
            f"TrustSphere Bank"
        )

    @staticmethod
    def _chart_evidence_list(
        citations: list[ChatCitation],
        score: RiskScore,
        case_data: dict[str, Any],
        activity: list[dict],
    ) -> list[ChatCitation]:
        ordered: list[ChatCitation] = []
        seen: set[str] = set()
        for item in citations:
            key = f"{item.kind}:{item.label}:{item.value}"
            if key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        for factor in sorted(score.factors, key=lambda f: f.score / f.max_score if f.max_score else 0, reverse=True)[:3]:
            key = f"factor:{factor.label}"
            if key in seen:
                continue
            seen.add(key)
            ordered.append(
                ChatCitation(
                    label=factor.label,
                    value=f"{factor.score:g}/{factor.max_score:g}",
                    source="RiskAssess factor evidence",
                    kind="factor",
                )
            )
        if activity:
            latest = activity[-1]
            key = "case_field:Latest activity period"
            if key not in seen:
                ordered.append(
                    ChatCitation(
                        label="Latest activity period",
                        value=f"{latest.get('period')}: {latest.get('total_amount')} ({latest.get('transaction_count')} txns)",
                        source="TRANSACTION activity",
                        kind="case_field",
                    )
                )
        if case_data.get("counterparty_history"):
            ordered.append(
                ChatCitation(
                    label="Counterparty history",
                    value=str(case_data["counterparty_history"]),
                    source="Mock case-data store",
                    kind="case_field",
                )
            )
        return ordered[:8]

    @staticmethod
    def _normalize_citations(
        raw: list[dict[str, str]],
        score: RiskScore,
        case_data: dict[str, Any],
        policy_hits: list[dict],
        chart: ChatChartSpec | None,
    ) -> list[ChatCitation]:
        allowed = {"factor", "evidence", "precedent", "policy", "case_field", "chart"}
        out: list[ChatCitation] = []
        for item in raw:
            kind = str(item.get("kind") or "evidence")
            if kind not in allowed:
                kind = "evidence"
            out.append(
                ChatCitation(
                    label=str(item.get("label") or "Citation"),
                    value=str(item.get("value") or ""),
                    source=str(item.get("source") or "case grounding"),
                    kind=kind,  # type: ignore[arg-type]
                )
            )
        if not out and score.factors:
            top = max(score.factors, key=lambda f: f.score / f.max_score if f.max_score else 0)
            out.append(
                ChatCitation(
                    label=top.key,
                    value=f"{top.score}/{top.max_score}",
                    source="RiskAssess factor evidence",
                    kind="factor",
                )
            )
        _ = case_data, policy_hits, chart
        return out[:8]
