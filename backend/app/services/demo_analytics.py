"""Deterministic 12-month operations series for demo / offline mode."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def build_demo_operations_dashboard(
    *,
    scored_queue_size: int = 6,
    high_priority_unresolved: int = 2,
    high_priority_exposure_usd: float = 7_150_000.0,
    unresolved_exposure_usd: float = 10_667_500.0,
    open_alerts: int = 4,
    investigating: int = 2,
) -> dict[str, Any]:
    """Return a realistic improving 12-month operations payload."""
    now = datetime.now(timezone.utc)
    months: list[dict[str, Any]] = []
    year, month = now.year, now.month

    for offset in range(11, -1, -1):
        m = month - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        progress = (11 - offset) / 11
        raised = int(160 + 18 * (1 - progress) + (offset % 3) * 4)
        closed = int(raised * (0.72 + 0.18 * progress) - (offset % 2))
        closed = max(0, min(raised + 20, closed))
        false_positives = int(closed * (0.78 - 0.12 * progress))
        true_positives = max(0, closed - false_positives)
        sla_breaches = int(raised * (0.34 - 0.16 * progress))
        transaction_value = round((48_000_000 + 6_000_000 * (1 - progress)) * (0.92 + 0.04 * (offset % 3)), 0)
        median_hours = round(56 - 34 * progress, 1)
        months.append(
            {
                "month": _month_key(y, m),
                "raised": raised,
                "closed": closed,
                "transaction_value_usd": float(transaction_value),
                "sla_breaches": max(0, sla_breaches),
                "false_positives": false_positives,
                "true_positives": true_positives,
                "median_review_hours": median_hours,
            }
        )

    period_raised = sum(point["raised"] for point in months)
    period_closed = sum(point["closed"] for point in months)
    period_fp = sum(point["false_positives"] for point in months)
    period_tp = sum(point["true_positives"] for point in months)
    period_sla = sum(point["sla_breaches"] for point in months)
    timeout_proxy = int(period_closed * 0.48)
    latest = months[-1]
    backlog_change = latest["raised"] - latest["closed"]
    median_review = months[-1]["median_review_hours"]

    return {
        "data_mode": "demo",
        "months": months,
        "kpis": {
            "backlog": open_alerts + investigating,
            "open_alerts": open_alerts,
            "investigating": investigating,
            "median_review_hours": median_review,
            "closure_rate": round(period_closed / period_raised, 3) if period_raised else 0.0,
            "sla_adherence_rate": round(1 - (period_sla / period_raised), 3) if period_raised else 0.0,
            "false_positive_rate": round(period_fp / (period_fp + period_tp), 3) if (period_fp + period_tp) else 0.0,
            "review_timeout_rate": round(timeout_proxy / period_raised, 3) if period_raised else 0.0,
            "high_priority_unresolved": high_priority_unresolved,
            "high_priority_exposure_usd": high_priority_exposure_usd,
            "unresolved_exposure_usd": unresolved_exposure_usd,
            "backlog_change": backlog_change,
            "period_raised": period_raised,
            "period_closed": period_closed,
            "scored_queue_size": scored_queue_size,
        },
        "notes": [
            "Demo series: illustrative 12-month operations trend, not live bank performance.",
            "Client baseline: manual review 1–3 days; AML false-positive rate reported at 90–95%.",
            "Backlog KPIs measure the ops population; the scored work queue is the prioritised subset for triage.",
            "High-priority unresolved count is computed from the scored queue subset.",
        ],
    }
