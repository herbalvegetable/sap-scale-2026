from __future__ import annotations

import logging
import re
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
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore

logger = logging.getLogger(__name__)

PROMPT_VERSION = "casechat-1.0"
ACTOR = "Amelia Reyes"

ACTION_PATTERNS = re.compile(
    r"\b(escalate\s+(this|it|the\s+alert)|clear\s+(this|it|the\s+alert)|"
    r"file\s+(a\s+)?sar|submit\s+(the\s+)?sar|block\s+(the\s+)?(payment|account)|"
    r"auto[- ]?(clear|escalate|file)|close\s+(this|the)\s+alert)\b",
    re.IGNORECASE,
)

CHAT_SYSTEM_PROMPT = """
You are RiskAssess Case Assistant for a single financial-crime alert. Answer ONLY
using the supplied grounding pack (score factors, evidence, case data, policy
passages, optional chart summary). Return JSON with:
reply (plain text for the investigator),
citations (array of {label, value, source, kind} where kind is one of
factor|evidence|precedent|policy|case_field|chart),
suggested_draft_snippet (string or null — only when the user asked to draft/refine notes),
refused_action (boolean),
refusal_reason (string or null).
Never invent facts. If data is missing, say so. Never clear, escalate, file a SAR,
or block a payment — if asked, set refused_action true and point the investigator
to Approve/Override on the Actionable Insights card. Do not change risk scores.
""".strip()


class ModelChatReply(BaseModel):
    reply: str = Field(min_length=10, max_length=2500)
    citations: list[dict[str, str]] = Field(default_factory=list)
    suggested_draft_snippet: str | None = None
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

        message = request.message.strip()
        score = self.scoring.score_alert(alert_id, refresh=False, use_ai=True)
        activity = self.repository.get_transaction_activity(str(context["company_id"]), score.total)
        case_data = get_case_evidence(alert_id, context)
        explanation = self.repository.get_explanation(alert_id)
        insight = self.repository.get_insight(alert_id)
        policy_hits = self.vector_store.search(f"{message} {context.get('alert_type', '')}", limit=3)

        refused = bool(ACTION_PATTERNS.search(message))
        chart_type = self._detect_chart_type(message)
        chart = self._build_chart(chart_type, context, score, activity, case_data) if chart_type else None

        grounding = {
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
            "signals": context.get("signals", {}),
            "score": score.model_dump(mode="json"),
            "activity_summary": [
                {"period": p.get("period"), "total_amount": p.get("total_amount"), "transaction_count": p.get("transaction_count")}
                for p in activity
            ],
            "case_evidence": {
                "counterparty_history": case_data.get("counterparty_history"),
                "prior_alerts": case_data.get("prior_alerts"),
                "transaction_metadata": case_data.get("transaction_metadata"),
                "sanctions_list_version": case_data.get("sanctions_list_version"),
                "related_transactions": case_data.get("related_transactions"),
                "prior_alert_summaries": case_data.get("prior_alert_summaries"),
                "precedents": [p.model_dump() if hasattr(p, "model_dump") else p for p in case_data.get("precedents", [])],
                "precedent_cases_detail": case_data.get("precedent_cases_detail"),
            },
            "explanation": explanation.model_dump(mode="json") if explanation else None,
            "insight": insight.model_dump(mode="json") if insight else None,
            "policy_passages": policy_hits,
            "chart": chart.model_dump(mode="json") if chart else None,
            "action_request_detected": refused,
            "history": [m.model_dump(mode="json") for m in self.repository.get_chat_thread(alert_id)[-12:]],
            "user_message": message,
        }

        if refused:
            synthesis = {
                "reply": (
                    "I can’t clear, escalate, file a SAR, or block a payment. "
                    "Use Approve or Override on the Actionable Insights recommendation card "
                    "so the disposition stays human-clicked and auditable."
                ),
                "citations": [],
                "suggested_draft_snippet": None,
                "refused_action": True,
                "refusal_reason": "Action requests are blocked; disposition must use Approve/Override controls.",
                "provenance": "fallback",
                "model": "guardrail-v1",
            }
        else:
            synthesis = self._synthesize(grounding)

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

        turn_id = f"TURN-{uuid.uuid4().hex[:10].upper()}"
        thread_id = f"THREAD-{alert_id}"
        now = datetime.now(timezone.utc)
        reply = str(synthesis["reply"])
        draft_snippet = synthesis.get("suggested_draft_snippet")
        refused_action = bool(synthesis.get("refused_action") or refused)
        refusal_reason = synthesis.get("refusal_reason") if refused_action else None

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
                f"Why is {top.key} ({top.label}) scored {top.score}/{top.max_score} "
                f"for this transaction? Cite the factor evidence and confidence."
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
                label="Refine my draft notes",
                prompt="Help refine my investigator draft notes using this case's evidence.",
            )
        else:
            company = context["company"]
            third = ChatSuggestion(
                id="policy_sla",
                label="What policy/SLA applies?",
                prompt=(
                    "What policy or SLA applies given "
                    f"PEP={company.get('pep')}, sanctions={company.get('sanctions_match')}, "
                    f"FATF={context.get('signals', {}).get('fatf_risk')} on this alert?"
                ),
            )
        return [why, second, third]

    @staticmethod
    def _greeting(alert_id: str) -> str:
        return (
            f"Hi Amelia — I’m your case assistant for {alert_id}. "
            "I can only reason over this transaction’s evidence, risk factors, precedent, and policy. "
            "Pick a suggestion below to generate an answer."
        )

    @staticmethod
    def _detect_chart_type(message: str) -> str | None:
        lower = message.lower()
        if "factor breakdown" in lower or "risk factor" in lower and "chart" in lower:
            return "factor_breakdown"
        if "precedent" in lower and ("chart" in lower or "graph" in lower or "outcome" in lower):
            return "precedent_outcomes"
        if any(token in lower for token in ("chart", "graph", "plot", "activity vs baseline", "against its baseline")):
            if "factor" in lower:
                return "factor_breakdown"
            if "precedent" in lower or "outcome" in lower:
                return "precedent_outcomes"
            return "activity_vs_baseline"
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
                source="TRANSACTION activity + TRANSACTION_BASELINES",
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
            for item in details:
                key = str(item.get("disposition") or item.get("outcome") or "unknown")
                counts[key] = counts.get(key, 0) + 1
            if not counts:
                for prec in case_data.get("precedents") or []:
                    data = prec.model_dump() if hasattr(prec, "model_dump") else prec
                    label = str(data.get("typical_outcome") or "typical_outcome")[:40]
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
                source="Mock case-data store (precedent cases)",
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
                "refused_action": generated.refused_action,
                "refusal_reason": generated.refusal_reason,
                "provenance": "ai",
                "model": self.settings.aicore_model_name,
            }
        except (AICoreError, ValidationError, ValueError, KeyError) as exc:
            logger.warning("Case chat synthesis failed; using fallback: %s", exc)
            return self._fallback_reply(grounding)

    def _fallback_reply(self, grounding: dict[str, Any]) -> dict[str, Any]:
        message = str(grounding.get("user_message") or "").lower()
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
        elif "draft" in message:
            top = sorted(factors, key=lambda f: float(f.get("score") or 0), reverse=True)[:2]
            cited = ", ".join(f"{f.get('key')}={f.get('score')}" for f in top) or "available factors"
            snippet = (
                f"[DRAFT — requires human edit/approval]\n"
                f"Alert {grounding['alert']['id']}: reviewed factors {cited}. "
                f"Counterparty history: {case.get('counterparty_history')}. "
                "No disposition has been submitted from chat."
            )
            reply = "Here is a draft note snippet you can insert into Actionable Insights for human edit/approval."
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
                        "label": str(top.get("key")),
                        "value": f"{top.get('score')}/{top.get('max_score')}",
                        "source": "RiskAssess factor evidence",
                        "kind": "factor",
                    }
                )
            else:
                reply = "Insufficient scored factors are available to answer that question for this alert."

        return {
            "reply": reply,
            "citations": citations,
            "suggested_draft_snippet": None,
            "refused_action": False,
            "refusal_reason": None,
            "provenance": "fallback",
            "model": "deterministic-chat-fallback-v1",
        }

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
