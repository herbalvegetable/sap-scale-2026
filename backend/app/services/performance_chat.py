from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models.schemas import (
    ChatChartSeries,
    ChatChartSpec,
    ChatCitation,
    ChatMessage,
    ChatSuggestion,
    OperationsDashboard,
    OperationsKpis,
    PerformanceChatAuditRecord,
    PerformanceChatRequest,
    PerformanceChatResponse,
    PerformanceChatThreadResponse,
    RangeMonths,
)
from app.services.ai_core_client import AICoreClient, AICoreError
from app.services.prompt_guard import (
    detects_disallowed_action,
    injection_system_addendum,
    sanitize_user_message,
    wrap_untrusted,
)
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)

PROMPT_VERSION = "perfchat-1.0"
ACTOR = "Amelia Reyes, Group Chief Risk Officer"

FORECAST_PATTERNS = re.compile(
    r"\b(forecast|predict|will\s+(we|it)|next\s+(month|quarter|year)|projection|"
    r"what\s+will\s+happen|extrapolat)\b",
    re.IGNORECASE,
)

METRIC_DEFINITIONS: dict[str, str] = {
    "backlog": "Open alerts plus investigating cases currently in the queue.",
    "median_review_hours": "Median hours from alert creation to first review disposition in the selected period.",
    "closure_rate": "Cases closed divided by cases raised in the selected period.",
    "sla_adherence_rate": "Share of raised cases that did not breach SLA in the selected period.",
    "review_timeout_rate": "Share of raised cases closed due to an expired review timeline (proxy).",
    "high_priority_unresolved": "High-tier scored alerts still open or investigating, with associated exposure.",
    "backlog_change": "Latest month raised minus closed; negative means the backlog is improving.",
    "false_positive_rate": "False positives divided by (false positives + true positives) in the period.",
    "transaction_value_usd": "Sum of alerted transaction value (USD) by month.",
    "sla_breaches": "Count of SLA breaches by month.",
    "raised": "Alerts raised in the month.",
    "closed": "Alerts closed in the month.",
}

CHAT_SYSTEM_PROMPT = (
    """
You are RiskAssess Performance Assistant for the operations performance dashboard.
The user is Amelia Reyes, Group Chief Risk Officer. Answer ONLY using the supplied grounding pack
(KPIs, monthly series for the selected 6M/12M range, metric definitions, dashboard notes, optional chart).
Return JSON with:
reply (plain English for the Group Chief Risk Officer — never snake_case keys, never key=value dumps, never JSON),
citations (array of {label, value, source, kind} where kind is one of
kpi|definition|chart|note|metric; labels and sources must be plain English),
refused_action (boolean),
refusal_reason (string or null).
Never invent facts or numbers. If data is missing, say so.
Distinguish observed dashboard values from client baselines/targets mentioned in notes.
Do not forecast future performance beyond the grounded series — if asked to predict, refuse and explain.
Never clear, escalate, file a SAR, reassign queues, or change operational dispositions — if asked,
set refused_action true and point the user to the case workflow controls.
When the user asks to show, compare, visualise, plot, chart, or see trends,
a chart may be attached; still explain the chart in reply using plain English metric names.
Always mention the selected range (6 or 12 months) when discussing period aggregates or trends.
""".strip()
    + "\n"
    + injection_system_addendum()
)


class ModelPerfChatReply(BaseModel):
    reply: str = Field(min_length=10, max_length=2500)
    citations: list[dict[str, str]] = Field(default_factory=list)
    refused_action: bool = False
    refusal_reason: str | None = None


class PerformanceChatService:
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

    def get_thread(self, range_months: RangeMonths = 12) -> PerformanceChatThreadResponse:
        dashboard = self._load_dashboard()
        scoped = self._scope_dashboard(dashboard, range_months)
        thread_id = self._thread_id(range_months)
        return PerformanceChatThreadResponse(
            range_months=range_months,
            messages=self.repository.get_performance_chat_thread(thread_id),
            suggestions=self.build_suggestions(scoped, range_months),
            greeting=self._greeting(range_months, scoped.data_mode),
        )

    def chat(self, request: PerformanceChatRequest) -> PerformanceChatResponse:
        range_months = request.range_months
        message = sanitize_user_message(request.message)
        dashboard = self._load_dashboard()
        scoped = self._scope_dashboard(dashboard, range_months)
        thread_id = self._thread_id(range_months)

        refused = detects_disallowed_action(message)
        forecast = bool(FORECAST_PATTERNS.search(message)) and not refused
        chart_type = None if refused or forecast else self._detect_chart_type(message)
        chart = self._build_chart(chart_type, scoped) if chart_type else None

        grounding = {
            "range_months": range_months,
            "data_mode": scoped.data_mode,
            "kpis": scoped.kpis.model_dump(mode="json"),
            "months": [point.model_dump(mode="json") for point in scoped.months],
            "metric_definitions": METRIC_DEFINITIONS,
            "notes": scoped.notes,
            "chart": chart.model_dump(mode="json") if chart else None,
            "action_request_detected": refused,
            "forecast_request_detected": forecast,
            "history": [
                m.model_dump(mode="json")
                for m in self.repository.get_performance_chat_thread(thread_id)[-12:]
            ],
            "user_message_plain": message,
            "user_message": wrap_untrusted("user_message", message),
        }

        if refused:
            synthesis = {
                "reply": (
                    "I can’t clear cases, escalate queues, file a SAR, or change operational dispositions. "
                    "Use the case command centre and Actionable Insights Approve/Override controls so "
                    "actions stay human-clicked and auditable."
                ),
                "citations": [],
                "refused_action": True,
                "refusal_reason": "Operational action requests are blocked in the performance assistant.",
                "provenance": "fallback",
                "model": "guardrail-v1",
            }
        elif forecast:
            synthesis = {
                "reply": (
                    f"I can’t forecast beyond the grounded {range_months}-month series. "
                    "I can explain observed trends, compare months, or chart the metrics already on this dashboard."
                ),
                "citations": self._kpi_citation_dicts(scoped.kpis, range_months)[:2],
                "refused_action": True,
                "refusal_reason": "Forecasts and unsupported projections are blocked.",
                "provenance": "fallback",
                "model": "guardrail-v1",
            }
        else:
            synthesis = self._synthesize(grounding)

        citations = self._normalize_citations(
            synthesis.get("citations") or [],
            scoped,
            chart,
            range_months,
        )
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
        now = datetime.now(timezone.utc)
        reply = str(synthesis["reply"])
        refused_action = bool(synthesis.get("refused_action") or refused or forecast)
        refusal_reason = synthesis.get("refusal_reason") if refused_action else None

        user_msg = ChatMessage(role="user", content=message, created_at=now)
        assistant_msg = ChatMessage(
            role="assistant",
            content=reply,
            citations=citations,
            chart=chart,
            created_at=now,
        )
        self.repository.append_performance_chat_messages(thread_id, [user_msg, assistant_msg])
        self.repository.append_performance_chat_audit(
            PerformanceChatAuditRecord(
                turn_id=turn_id,
                thread_id=thread_id,
                range_months=range_months,
                user_message=message,
                assistant_reply=reply,
                citations=citations,
                chart_type=chart.chart_type if chart else None,
                refused_action=refused_action,
                actor=ACTOR,
                created_at=now,
            )
        )

        return PerformanceChatResponse(
            range_months=range_months,
            reply=reply,
            citations=citations,
            chart=chart,
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
        dashboard: OperationsDashboard,
        range_months: RangeMonths,
    ) -> list[ChatSuggestion]:
        kpis = dashboard.kpis
        backlog_label = (
            f"Why is backlog {kpis.backlog}?"
            if kpis.backlog
            else "Explain current backlog"
        )
        return [
            ChatSuggestion(
                id="explain_backlog",
                label=backlog_label,
                prompt=(
                    f"Over the selected {range_months}-month window, explain the current backlog "
                    f"({kpis.backlog}: {kpis.open_alerts} open, {kpis.investigating} investigating), "
                    "closure rate, and backlog change. Cite the KPI values."
                ),
            ),
            ChatSuggestion(
                id="chart_raised_closed",
                label="Chart raised vs closed",
                prompt=(
                    f"Chart raised versus closed cases for the last {range_months} months "
                    "and explain what the trend implies for backlog pressure."
                ),
            ),
            ChatSuggestion(
                id="sla_trend",
                label="How is SLA exposure trending?",
                prompt=(
                    f"Using the last {range_months} months, how is SLA adherence and the monthly "
                    "SLA breach series trending? Cite the KPI and monthly figures."
                ),
            ),
        ]

    @staticmethod
    def _thread_id(range_months: RangeMonths) -> str:
        return f"PERF-{range_months}M"

    @staticmethod
    def _greeting(range_months: RangeMonths, data_mode: str) -> str:
        mode_label = "live HANA aggregates" if data_mode == "hana" else "demo operations series"
        return (
            f"Hi Amelia — I’m your performance assistant for the {range_months}-month operations view "
            f"({mode_label}). Ask about any KPI or chart on this dashboard, or pick a suggestion below."
        )

    def _load_dashboard(self) -> OperationsDashboard:
        contexts = self.repository.all_alert_contexts()
        high_priority_ids = {
            str(row["id"])
            for row in contexts
            if self.scoring.score_alert(str(row["id"]), use_ai=False).tier == "high"
            and str(row.get("status")).lower() in {"open", "investigating"}
        }
        payload = self.repository.get_operations_dashboard(high_priority_ids=high_priority_ids)
        return OperationsDashboard.model_validate(payload)

    @staticmethod
    def _scope_dashboard(dashboard: OperationsDashboard, range_months: RangeMonths) -> OperationsDashboard:
        months = dashboard.months[-range_months:]
        if len(months) == len(dashboard.months):
            return dashboard

        period_raised = sum(point.raised for point in months)
        period_closed = sum(point.closed for point in months)
        period_fp = sum(point.false_positives for point in months)
        period_tp = sum(point.true_positives for point in months)
        period_sla = sum(point.sla_breaches for point in months)
        timeout_proxy = int(period_closed * 0.48)
        latest = months[-1] if months else None
        backlog_change = (latest.raised - latest.closed) if latest else 0
        median_review = latest.median_review_hours if latest else dashboard.kpis.median_review_hours

        kpis = dashboard.kpis.model_copy(
            update={
                "median_review_hours": median_review,
                "closure_rate": round(period_closed / period_raised, 3) if period_raised else 0.0,
                "sla_adherence_rate": round(1 - (period_sla / period_raised), 3) if period_raised else 0.0,
                "false_positive_rate": (
                    round(period_fp / (period_fp + period_tp), 3) if (period_fp + period_tp) else 0.0
                ),
                "review_timeout_rate": round(timeout_proxy / period_raised, 3) if period_raised else 0.0,
                "backlog_change": backlog_change,
                "period_raised": period_raised,
                "period_closed": period_closed,
            }
        )
        return OperationsDashboard(
            data_mode=dashboard.data_mode,
            months=months,
            kpis=kpis,
            notes=dashboard.notes,
        )

    @staticmethod
    def _detect_chart_type(message: str) -> str | None:
        lower = message.lower()
        visual_intent = any(
            token in lower
            for token in ("chart", "graph", "plot", "visuali", "show me", "display", "draw", "illustrate")
        )
        sla_intent = any(token in lower for token in ("sla", "breach", "adherence"))
        value_intent = any(
            token in lower
            for token in ("transaction value", "alerted value", "exposure under review", "usd value")
        )
        raised_closed_intent = any(
            token in lower
            for token in ("raised vs", "raised versus", "raised and closed", "backlog pressure", "throughput")
        ) or ("raised" in lower and "closed" in lower)
        closed_intent = "closed" in lower and "raised" not in lower

        if raised_closed_intent and (visual_intent or "trend" in lower or "how" in lower):
            return "raised_vs_closed"
        if sla_intent and (visual_intent or "trend" in lower or "month" in lower):
            return "sla_breaches"
        if value_intent and (visual_intent or "trend" in lower or "month" in lower):
            return "transaction_value"
        if closed_intent and (visual_intent or "by month" in lower):
            return "closed_by_month"
        if visual_intent:
            if sla_intent:
                return "sla_breaches"
            if value_intent:
                return "transaction_value"
            if "closed" in lower and "raised" not in lower:
                return "closed_by_month"
            return "raised_vs_closed"
        if raised_closed_intent:
            return "raised_vs_closed"
        if sla_intent and ("trend" in lower or "month" in lower):
            return "sla_breaches"
        return None

    def _build_chart(self, chart_type: str | None, dashboard: OperationsDashboard) -> ChatChartSpec | None:
        if not chart_type or not dashboard.months:
            return None
        points = [
            {
                "month": point.month,
                "raised": point.raised,
                "closed": point.closed,
                "transaction_value_usd": point.transaction_value_usd,
                "sla_breaches": point.sla_breaches,
            }
            for point in dashboard.months
        ]
        if chart_type == "closed_by_month":
            return ChatChartSpec(
                chart_type="closed_by_month",
                title="Cases closed by month",
                x_key="month",
                series=[ChatChartSeries(key="closed", label="Closed", type="bar")],
                points=points,
                source="Operations monthly series",
                citation_label="Closed cases series",
            )
        if chart_type == "raised_vs_closed":
            return ChatChartSpec(
                chart_type="raised_vs_closed",
                title="Raised vs closed by month",
                x_key="month",
                series=[
                    ChatChartSeries(key="raised", label="Raised", type="bar"),
                    ChatChartSeries(key="closed", label="Closed", type="line"),
                ],
                points=points,
                source="Operations monthly series",
                citation_label="Raised vs closed series",
            )
        if chart_type == "sla_breaches":
            return ChatChartSpec(
                chart_type="sla_breaches",
                title="SLA breaches by month",
                x_key="month",
                series=[ChatChartSeries(key="sla_breaches", label="SLA breaches", type="bar")],
                points=points,
                source="Operations monthly series",
                citation_label="SLA breach series",
            )
        if chart_type == "transaction_value":
            return ChatChartSpec(
                chart_type="transaction_value",
                title="Alerted transaction value by month",
                x_key="month",
                series=[
                    ChatChartSeries(key="transaction_value_usd", label="Alerted value (USD)", type="bar")
                ],
                points=points,
                currency="USD",
                source="Operations monthly series",
                citation_label="Alerted transaction value series",
            )
        return None

    def _synthesize(self, grounding: dict[str, Any]) -> dict[str, Any]:
        try:
            generated = ModelPerfChatReply.model_validate(
                self.ai_core.chat_json(CHAT_SYSTEM_PROMPT, grounding)
            )
            return {
                "reply": generated.reply,
                "citations": generated.citations,
                "refused_action": generated.refused_action,
                "refusal_reason": generated.refusal_reason,
                "provenance": "ai",
                "model": self.settings.aicore_model_name,
            }
        except (AICoreError, ValidationError, ValueError, KeyError) as exc:
            logger.warning("Performance chat synthesis failed; using fallback: %s", exc)
            return self._fallback_reply(grounding)

    def _fallback_reply(self, grounding: dict[str, Any]) -> dict[str, Any]:
        message = str(grounding.get("user_message_plain") or grounding.get("user_message") or "").lower()
        if "begin_untrusted" in message:
            start = message.find("]\n")
            end = message.find("\nend_untrusted")
            if start != -1 and end != -1 and end > start:
                message = message[start + 2 : end].strip()
        range_months = int(grounding.get("range_months") or 12)
        kpis = grounding.get("kpis") or {}
        months = grounding.get("months") or []
        notes = grounding.get("notes") or []
        chart = grounding.get("chart")
        citations: list[dict[str, str]] = []

        if chart:
            reply = (
                f"Here is a grounded {range_months}-month chart: {chart.get('title')}. "
                f"Data source: {chart.get('source')}. "
                "All points come from the operations series — none were invented."
            )
            citations.append(
                {
                    "label": str(chart.get("citation_label") or "Chart"),
                    "value": str(chart.get("title")),
                    "source": str(chart.get("source")),
                    "kind": "chart",
                }
            )
        elif "sla" in message:
            adherence = float(kpis.get("sla_adherence_rate") or 0)
            latest_breaches = int(months[-1]["sla_breaches"]) if months else 0
            first_breaches = int(months[0]["sla_breaches"]) if months else 0
            direction = "improving" if latest_breaches < first_breaches else "worsening or flat"
            reply = (
                f"Over the last {range_months} months, SLA adherence is {adherence:.1%}. "
                f"Monthly breaches moved from {first_breaches} to {latest_breaches} ({direction}). "
                "SLA adherence is the share of raised cases without a breach in the period."
            )
            citations.extend(
                [
                    {
                        "label": "SLA adherence",
                        "value": f"{adherence:.1%}",
                        "source": "Operations KPIs",
                        "kind": "kpi",
                    },
                    {
                        "label": "SLA adherence definition",
                        "value": METRIC_DEFINITIONS["sla_adherence_rate"],
                        "source": "Metric definitions",
                        "kind": "definition",
                    },
                ]
            )
        elif "backlog" in message or "closure" in message:
            backlog = int(kpis.get("backlog") or 0)
            closure = float(kpis.get("closure_rate") or 0)
            change = int(kpis.get("backlog_change") or 0)
            change_txt = f"+{change}" if change > 0 else str(change)
            reply = (
                f"Current backlog is {backlog} "
                f"({int(kpis.get('open_alerts') or 0)} open, {int(kpis.get('investigating') or 0)} investigating). "
                f"Closure rate over {range_months} months is {closure:.1%}, "
                f"and latest-month backlog change is {change_txt} (raised minus closed)."
            )
            citations.extend(
                [
                    {
                        "label": "Current backlog",
                        "value": str(backlog),
                        "source": "Operations KPIs",
                        "kind": "kpi",
                    },
                    {
                        "label": "Closure rate",
                        "value": f"{closure:.1%}",
                        "source": "Operations KPIs",
                        "kind": "kpi",
                    },
                    {
                        "label": "Backlog change",
                        "value": change_txt,
                        "source": "Operations KPIs",
                        "kind": "kpi",
                    },
                ]
            )
        elif "review" in message or "median" in message:
            hours = kpis.get("median_review_hours")
            if hours is None:
                reply = f"Median review time is unavailable for the {range_months}-month view."
            else:
                hours_f = float(hours)
                display = f"{hours_f:.1f}h" if hours_f < 24 else f"{hours_f / 24:.1f}d"
                reply = (
                    f"Median review time is {display} in the selected {range_months}-month window. "
                    f"{METRIC_DEFINITIONS['median_review_hours']} "
                    "Client baseline noted on the dashboard is typically 1–3 days with a target under 24 hours."
                )
                citations.append(
                    {
                        "label": "Median review time",
                        "value": display,
                        "source": "Operations KPIs",
                        "kind": "kpi",
                    }
                )
        elif "high-priority" in message or "high priority" in message or "exposure" in message:
            unresolved = int(kpis.get("high_priority_unresolved") or 0)
            exposure = float(kpis.get("high_priority_exposure_usd") or 0)
            reply = (
                f"There are {unresolved} high-priority unresolved cases "
                f"(${exposure:,.0f} exposure) against a scored queue of "
                f"{int(kpis.get('scored_queue_size') or 0)}. "
                f"{METRIC_DEFINITIONS['high_priority_unresolved']}"
            )
            citations.append(
                {
                    "label": "High-priority unresolved",
                    "value": f"{unresolved} · ${exposure:,.0f}",
                    "source": "Operations KPIs",
                    "kind": "kpi",
                }
            )
        elif "timeout" in message:
            rate = float(kpis.get("review_timeout_rate") or 0)
            reply = (
                f"Review-timeout rate is {rate:.1%} over the last {range_months} months. "
                f"{METRIC_DEFINITIONS['review_timeout_rate']}"
            )
            citations.append(
                {
                    "label": "Review-timeout rate",
                    "value": f"{rate:.1%}",
                    "source": "Operations KPIs",
                    "kind": "kpi",
                }
            )
        elif "false positive" in message or "false-positive" in message:
            rate = float(kpis.get("false_positive_rate") or 0)
            reply = (
                f"False-positive rate is {rate:.1%} over the last {range_months} months. "
                f"{METRIC_DEFINITIONS['false_positive_rate']}"
            )
            citations.append(
                {
                    "label": "False-positive rate",
                    "value": f"{rate:.1%}",
                    "source": "Operations KPIs",
                    "kind": "kpi",
                }
            )
        elif "note" in message or "baseline" in message or "pain point" in message:
            note = notes[0] if notes else "No dashboard notes are available."
            reply = (
                f"Dashboard notes for this {range_months}-month view: {note} "
                "Treat baselines in notes as client context, not as values computed from this series."
            )
            citations.append(
                {
                    "label": "Dashboard note",
                    "value": str(note),
                    "source": "Operations dashboard notes",
                    "kind": "note",
                }
            )
        else:
            raised = int(kpis.get("period_raised") or 0)
            closed = int(kpis.get("period_closed") or 0)
            closure = float(kpis.get("closure_rate") or 0)
            reply = (
                f"In the selected {range_months}-month window, {raised:,} cases were raised and "
                f"{closed:,} closed (closure rate {closure:.1%}). "
                f"Current backlog is {int(kpis.get('backlog') or 0)}. "
                "Ask about a specific KPI, trend, or request a chart for more detail."
            )
            citations.extend(self._kpi_citation_dicts_from_dict(kpis, range_months)[:3])

        return {
            "reply": reply,
            "citations": citations,
            "refused_action": False,
            "refusal_reason": None,
            "provenance": "fallback",
            "model": "deterministic-perf-chat-fallback-v1",
        }

    @staticmethod
    def _kpi_citation_dicts(kpis: OperationsKpis, range_months: RangeMonths) -> list[dict[str, str]]:
        return PerformanceChatService._kpi_citation_dicts_from_dict(
            kpis.model_dump(mode="json"),
            range_months,
        )

    @staticmethod
    def _kpi_citation_dicts_from_dict(kpis: dict[str, Any], range_months: int) -> list[dict[str, str]]:
        return [
            {
                "label": "Current backlog",
                "value": str(kpis.get("backlog")),
                "source": f"Operations KPIs ({range_months}M)",
                "kind": "kpi",
            },
            {
                "label": "Closure rate",
                "value": f"{float(kpis.get('closure_rate') or 0):.1%}",
                "source": f"Operations KPIs ({range_months}M)",
                "kind": "kpi",
            },
            {
                "label": "SLA adherence",
                "value": f"{float(kpis.get('sla_adherence_rate') or 0):.1%}",
                "source": f"Operations KPIs ({range_months}M)",
                "kind": "kpi",
            },
        ]

    def _normalize_citations(
        self,
        raw: list[dict[str, str]],
        dashboard: OperationsDashboard,
        chart: ChatChartSpec | None,
        range_months: RangeMonths,
    ) -> list[ChatCitation]:
        allowed = {"kpi", "definition", "chart", "note", "metric"}
        normalized: list[ChatCitation] = []
        seen: set[tuple[str, str, str]] = set()
        for item in raw:
            kind = str(item.get("kind") or "kpi")
            if kind not in allowed:
                kind = "kpi"
            label = str(item.get("label") or "Metric").strip()[:80]
            value = str(item.get("value") or "").strip()[:400]
            source = str(item.get("source") or "Operations dashboard").strip()[:120]
            key = (label, value, source)
            if not value or key in seen:
                continue
            seen.add(key)
            normalized.append(ChatCitation(label=label, value=value, source=source, kind=kind))  # type: ignore[arg-type]

        if not normalized:
            normalized.extend(
                ChatCitation.model_validate(item)
                for item in self._kpi_citation_dicts(dashboard.kpis, range_months)[:2]
            )
        if chart and not any(c.kind == "chart" for c in normalized):
            normalized.insert(
                0,
                ChatCitation(
                    label=chart.citation_label,
                    value=chart.title,
                    source=chart.source,
                    kind="chart",
                ),
            )
        return normalized[:8]
