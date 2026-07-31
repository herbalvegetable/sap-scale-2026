from __future__ import annotations

import json
import logging
from threading import Lock

from app.config import ROOT_DIR, Settings
from app.models.schemas import (
    ActionableInsight,
    AuditEvent,
    ChatAuditRecord,
    ChatMessage,
    Explanation,
    InsightDecisionRecord,
    PerformanceChatAuditRecord,
    RiskScore,
)
from app.services.demo_analytics import build_demo_operations_dashboard
from app.services.demo_data import get_demo_alerts
from app.services.hana_client import HanaClient
from app.services.privacy import privacy_meta

logger = logging.getLogger(__name__)

SCORED_QUEUE_CAP = 250
AUDIT_LOAD_LIMIT = 500


class RiskRepository:
    """Repository facade with a visible, reliable demo fallback."""

    def __init__(self, settings: Settings, hana: HanaClient) -> None:
        self.settings = settings
        self.hana = hana
        self._scores: dict[str, RiskScore] = {}
        self._explanations: dict[str, Explanation] = {}
        self._insights: dict[str, ActionableInsight] = {}
        self._insight_audit_log: list[InsightDecisionRecord] = []
        self._chat_threads: dict[str, list[ChatMessage]] = {}
        self._chat_audit_log: list[ChatAuditRecord] = []
        self._performance_chat_threads: dict[str, list[ChatMessage]] = {}
        self._performance_chat_audit_log: list[PerformanceChatAuditRecord] = []
        self._contexts: list[dict] | None = None
        self._lock = Lock()
        self._mode: str | None = None
        self._audit_path = ROOT_DIR / "backend" / "data" / "audit.jsonl"
        self._load_audit_from_disk()

    @property
    def mode(self) -> str:
        if self._mode:
            return self._mode
        if self.settings.data_mode == "demo":
            self._mode = "demo"
        elif self.settings.data_mode == "hana":
            self._mode = "hana" if self.hana.ping() else "demo"
        else:
            self._mode = "hana" if self.hana.ping() else "demo"
        return self._mode

    def all_alert_contexts(self) -> list[dict]:
        if self._contexts is not None:
            return self._contexts
        if self.mode == "hana":
            try:
                rows = self._load_hana_alerts()
                if rows:
                    self._contexts = rows
                    return rows
            except Exception as exc:
                logger.warning("Live alert query failed; using demo dataset: %s", exc)
                self._mode = "demo"
        self._contexts = get_demo_alerts()
        for row in self._contexts:
            raw_status = str(row.get("status") or "OPEN").upper()
            row["raw_status"] = raw_status
            row["status"] = "investigating" if "REVIEW" in raw_status or "INVESTIGAT" in raw_status else "open"
            row["status_label"] = row["status"].capitalize()
            row["status_reason"] = None
            row["sla_breached"] = bool(row.get("sla_breached", False))
            row["integration"] = {
                "source": "demo",
                "normalised_status": row["status"],
                "raw_status": raw_status,
                "scored_queue_cap": SCORED_QUEUE_CAP,
                "privacy_region": privacy_meta()["region"],
            }
        return self._contexts

    def get_alert_context(self, alert_id: str) -> dict | None:
        return next((row for row in self.all_alert_contexts() if str(row["id"]) == alert_id), None)

    def update_alert_status(self, alert_id: str, status: str) -> dict | None:
        """Update case status in the in-memory alert context (session-scoped)."""
        requested = status.lower().strip()
        allowed = {"open", "investigating", "closed", "closed_timeout"}
        if requested not in allowed:
            raise ValueError(f"Unsupported status: {status}")
        with self._lock:
            context = self.get_alert_context(alert_id)
            if context is None:
                return None
            if requested == "closed_timeout":
                context["status"] = "closed"
                context["status_label"] = "Closed"
                context["raw_status"] = "CLOSED_FALSE"
                context["status_reason"] = "Closed – Closed due to expired review timeline"
                context["sla_breached"] = True
            elif requested == "closed":
                context["status"] = "closed"
                context["status_label"] = "Closed"
                context["raw_status"] = "CLOSED"
                context["status_reason"] = "Closed – Resolved by team"
                context["sla_breached"] = False
            else:
                context["status"] = requested
                context["status_label"] = requested.capitalize()
                context["raw_status"] = requested.upper()
                context["status_reason"] = None
                context["sla_breached"] = False
            return dict(context)

    def _load_hana_alerts(self) -> list[dict]:
        """Map the discovered TrustSphere views to the canonical API shape."""
        schema = self.settings.reference_schema
        sql = f"""
            SELECT
                A.ALERT_ID AS ID,
                A.TRANSACTION_ID,
                A.COMPANY_ID,
                C.LEGAL_NAME AS COMPANY_NAME,
                A.ALERT_TYPE,
                A.ALERT_SUBTYPE,
                A.STATUS,
                A.ALERT_DESCRIPTION AS DESCRIPTION,
                A.RESOLUTION_CODE,
                A.RESOLUTION_NOTES,
                A.RESOLVED_BY,
                A.RESOLVED_AT,
                A.SLA_DUE_AT,
                A.SLA_BREACHED,
                T.AMOUNT_USD AS AMOUNT,
                T.CURRENCY_ORIGINAL AS CURRENCY,
                OC.COUNTRY_NAME AS ORIGIN_COUNTRY,
                DC.COUNTRY_NAME AS DESTINATION_COUNTRY,
                A.CREATED_AT,
                T.INITIATED_AT AS OCCURRED_AT,
                T.BENEFICIARY_NAME AS COUNTERPARTY,
                T.TRANSACTION_TYPE AS CHANNEL,
                T.PAYMENT_PURPOSE AS PURPOSE,
                C.KYC_RISK_RATING AS RISK_RATING,
                C.PEP_ASSOCIATED,
                C.SANCTIONS_HIT,
                C.ADVERSE_MEDIA_FLAG,
                I.INDUSTRY_NAME AS INDUSTRY,
                P.COMPOSITE_RISK_SCORE,
                P.OWNERSHIP_RISK_SCORE,
                P.TRANSACTION_RISK_SCORE,
                P.BEHAVIORAL_RISK_SCORE,
                P.REQUIRES_EDD,
                COALESCE(BO.OWNER_COUNT, 0) AS OWNER_COUNT,
                COALESCE(BO.PEP_COUNT, 0) AS OWNER_PEP_COUNT,
                COALESCE(BO.SANCTIONS_COUNT, 0) AS OWNER_SANCTIONS_COUNT,
                COALESCE(B.AVG_AMOUNT_USD, 0) AS BASELINE_AVG_AMOUNT,
                COALESCE(B.AVG_DAILY_COUNT, 0) AS BASELINE_DAILY_COUNT,
                COALESCE(CC.PRIOR_CASES, 0) AS PRIOR_CASES,
                COALESCE(CC.SAR_CASES, 0) AS SAR_CASES,
                DC.RISK_TIER AS COUNTRY_RISK_TIER,
                DC.FATF_STATUS,
                R.IS_HIGH_RISK AS HIGH_RISK_REGION,
                T.IS_CROSS_BORDER
            FROM {schema}.RISK_ALERTS A
            JOIN {schema}.TRANSACTIONS T ON T.TRANSACTION_ID = A.TRANSACTION_ID
            LEFT JOIN {schema}.COMPANIES C ON C.COMPANY_ID = A.COMPANY_ID
            LEFT JOIN {schema}.INDUSTRIES I ON I.INDUSTRY_ID = C.INDUSTRY_ID
            LEFT JOIN {schema}.COUNTRIES OC ON OC.COUNTRY_ID = T.ORIGINATING_COUNTRY_ID
            LEFT JOIN {schema}.COUNTRIES DC ON DC.COUNTRY_ID = T.DESTINATION_COUNTRY_ID
            LEFT JOIN {schema}.REGIONS R ON R.REGION_ID = DC.REGION_ID
            LEFT JOIN {schema}.COMPANY_RISK_PROFILES P ON P.COMPANY_ID = A.COMPANY_ID
            LEFT JOIN (
                SELECT COMPANY_ID, COUNT(*) AS OWNER_COUNT,
                       SUM(CASE WHEN IS_PEP = TRUE THEN 1 ELSE 0 END) AS PEP_COUNT,
                       SUM(CASE WHEN SANCTIONS_MATCH = TRUE THEN 1 ELSE 0 END) AS SANCTIONS_COUNT
                FROM {schema}.COMPANY_BENEFICIAL_OWNERS
                GROUP BY COMPANY_ID
            ) BO ON BO.COMPANY_ID = A.COMPANY_ID
            LEFT JOIN (
                SELECT COMPANY_ID, AVG(AVG_AMOUNT_USD) AS AVG_AMOUNT_USD,
                       AVG(AVG_DAILY_COUNT) AS AVG_DAILY_COUNT
                FROM {schema}.TRANSACTION_BASELINES
                GROUP BY COMPANY_ID
            ) B ON B.COMPANY_ID = A.COMPANY_ID
            LEFT JOIN (
                SELECT COMPANY_ID, COUNT(*) AS PRIOR_CASES,
                       SUM(CASE WHEN SAR_FILED = TRUE THEN 1 ELSE 0 END) AS SAR_CASES
                FROM {schema}.COMPLIANCE_CASES
                GROUP BY COMPANY_ID
            ) CC ON CC.COMPANY_ID = A.COMPANY_ID
            ORDER BY A.CREATED_AT DESC
            LIMIT 250
        """
        rows = self.hana.query(sql)
        return [self._canonical_live_row(row) for row in rows]

    @staticmethod
    def _canonical_live_row(row: dict) -> dict:
        raw_status = str(row.get("status") or "OPEN").upper()
        if raw_status.startswith("CLOSED"):
            status = "closed"
            # CLOSED_FALSE = closed because manual review took too long (SLA timeout).
            if (
                raw_status in {"CLOSED_FALSE", "CLOSED-FALSE"}
                or "TIMEOUT" in raw_status
                or (bool(row.get("sla_breached")) and not row.get("resolved_by"))
            ):
                status_reason = "Closed – Closed due to expired review timeline"
            else:
                status_reason = "Closed – Resolved by team"
        elif raw_status in {"INVESTIGATING", "IN_REVIEW", "IN REVIEW"}:
            status = "investigating"
            status_reason = None
        else:
            status = "open"
            status_reason = None
        return {
            **row,
            "id": str(row["id"]),
            "transaction_id": str(row["transaction_id"]),
            "company_id": str(row.get("company_id") or "UNKNOWN"),
            "company_name": str(row.get("company_name") or "Unknown entity"),
            "description": str(row.get("description") or row.get("alert_type") or "Transaction monitoring alert"),
            "status": status,
            "raw_status": raw_status,
            "status_label": status.capitalize(),
            "status_reason": status_reason,
            "sla_breached": bool(row.get("sla_breached")),
            "transaction": {
                "counterparty": str(row.get("counterparty") or "Unknown counterparty"),
                "occurred_at": row["occurred_at"],
                "channel": str(row.get("channel") or "Unknown"),
                "purpose": str(row.get("purpose") or "Not supplied"),
            },
            "company": {
                "industry": str(row.get("industry") or "Not supplied"),
                "country": str(row.get("origin_country") or "Unknown"),
                "risk_rating": str(row.get("risk_rating") or "Unknown"),
                "pep": bool(row.get("pep_associated")) or int(row.get("owner_pep_count") or 0) > 0,
                "sanctions_match": bool(row.get("sanctions_hit")) or int(row.get("owner_sanctions_count") or 0) > 0,
                "beneficial_owner_layers": int(row.get("owner_count") or 0),
                "prior_cases": int(row.get("prior_cases") or 0),
                "baseline_average_amount": float(row.get("baseline_avg_amount") or 0),
                "baseline_monthly_frequency": float(row.get("baseline_daily_count") or 0) * 30,
                "adverse_media": bool(row.get("adverse_media_flag")),
                "requires_edd": bool(row.get("requires_edd")),
            },
            "signals": {
                "rapid_transfers": 0,
                "amount_ratio": (
                    float(row.get("amount") or 0) / float(row.get("baseline_avg_amount"))
                    if float(row.get("baseline_avg_amount") or 0) > 0
                    else 1
                ),
                "fatf_risk": str(row.get("country_risk_tier") or row.get("fatf_status") or "Unknown"),
                "supervisory_attention": bool(row.get("high_risk_region")),
                "new_corridor": bool(row.get("is_cross_border")) and str(row.get("country_risk_tier")).upper() != "LOW",
                "composite_profile_score": float(row.get("composite_risk_score") or 0),
                "ownership_risk_score": float(row.get("ownership_risk_score") or 0),
                "transaction_risk_score": float(row.get("transaction_risk_score") or 0),
                "behavioral_risk_score": float(row.get("behavioral_risk_score") or 0),
                "sar_cases": int(row.get("sar_cases") or 0),
            },
            "integration": {
                "source": "hana",
                "normalised_status": status,
                "raw_status": raw_status,
                "scored_queue_cap": SCORED_QUEUE_CAP,
                "privacy_region": privacy_meta()["region"],
            },
        }

    def get_beneficial_owners(self, company_id: str) -> list[dict]:
        if self.mode != "hana":
            return []
        schema = self.settings.reference_schema
        try:
            return self.hana.query(
                f"""
                SELECT
                    BO.OWNER_ID AS ID,
                    BO.OWNER_NAME AS NAME,
                    BO.OWNERSHIP_PERCENTAGE,
                    BO.IS_PEP,
                    BO.SANCTIONS_MATCH,
                    COALESCE(NC.COUNTRY_NAME, 'Not supplied') AS NATIONALITY,
                    COALESCE(RC.COUNTRY_NAME, 'Not supplied') AS RESIDENCE
                FROM {schema}.COMPANY_BENEFICIAL_OWNERS BO
                LEFT JOIN {schema}.COUNTRIES NC ON NC.COUNTRY_ID = BO.NATIONALITY_COUNTRY_ID
                LEFT JOIN {schema}.COUNTRIES RC ON RC.COUNTRY_ID = BO.RESIDENCE_COUNTRY_ID
                WHERE BO.COMPANY_ID = ?
                ORDER BY BO.OWNERSHIP_PERCENTAGE DESC
                """,
                (int(company_id),),
            )
        except Exception as exc:
            logger.warning("Could not retrieve beneficial owners for company %s: %s", company_id, exc)
            return []

    def get_transaction_activity(self, company_id: str, risk_level: float) -> list[dict]:
        if self.mode != "hana":
            context = next(
                (item for item in self.all_alert_contexts() if str(item["company_id"]) == company_id),
                None,
            )
            if context is None:
                return []
            return self._demo_activity_series(context, risk_level)
        schema = self.settings.reference_schema
        try:
            rows = self.hana.query(
                f"""
                SELECT * FROM (
                    SELECT
                        TO_VARCHAR(INITIATED_AT, 'YYYY-MM') AS PERIOD,
                        COUNT(*) AS TRANSACTION_COUNT,
                        SUM(AMOUNT_USD) AS TOTAL_AMOUNT,
                        AVG(AMOUNT_USD) AS AVERAGE_AMOUNT
                    FROM {schema}.TRANSACTIONS
                    WHERE ORIGINATOR_COMPANY_ID = ? OR BENEFICIARY_COMPANY_ID = ?
                    GROUP BY TO_VARCHAR(INITIATED_AT, 'YYYY-MM')
                    ORDER BY PERIOD DESC
                    LIMIT 12
                ) RECENT_ACTIVITY
                ORDER BY PERIOD ASC
                """,
                (int(company_id), int(company_id)),
            )
            return [{**row, "risk_level": risk_level} for row in rows]
        except Exception as exc:
            logger.warning("Could not retrieve transaction activity for company %s: %s", company_id, exc)
            return []

    @staticmethod
    def _demo_activity_series(context: dict, risk_level: float) -> list[dict]:
        """Build a short synthetic history for demo charts (grounded on baseline + current amount)."""
        from calendar import monthrange
        from datetime import datetime, timezone

        occurred = context["transaction"]["occurred_at"]
        if not isinstance(occurred, datetime):
            occurred = datetime.now(timezone.utc)
        baseline = float(context["company"].get("baseline_average_amount") or context["amount"])
        current = float(context["amount"])
        freq = max(1, int(context["company"].get("baseline_monthly_frequency") or 4))
        year, month = occurred.year, occurred.month
        points: list[dict] = []
        for offset in range(5, -1, -1):
            m = month - offset
            y = year
            while m <= 0:
                m += 12
                y -= 1
            blend = 0.15 * (5 - offset)
            total = baseline * (0.85 + 0.08 * ((5 - offset) % 3)) * (1 - blend) + current * blend
            count = max(1, freq - (offset % 3))
            points.append(
                {
                    "period": f"{y:04d}-{m:02d}",
                    "transaction_count": count,
                    "total_amount": round(total, 2),
                    "average_amount": round(total / count, 2),
                    "risk_level": risk_level if offset == 0 else max(10.0, risk_level * (0.55 + 0.08 * (5 - offset))),
                }
            )
            _ = monthrange(y, m)  # validate calendar month
        return points

    def get_operations_dashboard(self, high_priority_ids: set[str] | None = None) -> dict:
        """Aggregate 12-month operations KPIs from HANA or deterministic demo history."""
        contexts = self.all_alert_contexts()
        open_alerts = sum(str(row.get("status")).lower() == "open" for row in contexts)
        investigating = sum(str(row.get("status")).lower() == "investigating" for row in contexts)
        unresolved = [row for row in contexts if str(row.get("status")).lower() in {"open", "investigating"}]
        unresolved_exposure = sum(float(row.get("amount") or 0) for row in unresolved)
        priority_ids = high_priority_ids or set()
        high_unresolved = [row for row in unresolved if str(row.get("id")) in priority_ids]
        high_exposure = sum(float(row.get("amount") or 0) for row in high_unresolved)

        if self.mode == "hana":
            try:
                payload = self._load_hana_operations_dashboard()
                payload["kpis"].update(
                    {
                        "backlog": open_alerts + investigating,
                        "open_alerts": open_alerts,
                        "investigating": investigating,
                        "high_priority_unresolved": len(high_unresolved),
                        "high_priority_exposure_usd": round(high_exposure, 2),
                        "unresolved_exposure_usd": round(unresolved_exposure, 2),
                        "scored_queue_size": len(contexts),
                    }
                )
                payload["data_mode"] = "hana"
                notes = list(payload.get("notes") or [])
                notes.append(
                    f"Backlog KPIs cover the full ops population; the scored work queue is a prioritised "
                    f"subset (cap {SCORED_QUEUE_CAP}, currently {len(contexts)} cases) so investigators "
                    "triage highest SLA/regulatory exposure first."
                )
                notes.append(
                    f"High-priority unresolved count uses the scored queue subset ({len(contexts)} recent cases), "
                    "not the full alert population."
                )
                payload["notes"] = notes
                return payload
            except Exception as exc:
                logger.warning("Operations analytics HANA aggregation failed; using demo series: %s", exc)

        return build_demo_operations_dashboard(
            scored_queue_size=len(contexts),
            high_priority_unresolved=len(high_unresolved) or 2,
            high_priority_exposure_usd=round(high_exposure, 2) if high_unresolved else 7_150_000.0,
            unresolved_exposure_usd=round(unresolved_exposure, 2) if unresolved else 10_667_500.0,
            open_alerts=open_alerts or 4,
            investigating=investigating or 2,
        )

    def _load_hana_operations_dashboard(self) -> dict:
        schema = self.settings.reference_schema
        team_schema = self.settings.hana_schema
        monthly_sql = f"""
            SELECT * FROM (
                SELECT
                    TO_VARCHAR(A.CREATED_AT, 'YYYY-MM') AS MONTH,
                    COUNT(*) AS RAISED,
                    SUM(CASE WHEN UPPER(A.STATUS) LIKE 'CLOSED%' THEN 1 ELSE 0 END) AS CLOSED,
                    COALESCE(SUM(T.AMOUNT_USD), 0) AS TRANSACTION_VALUE_USD,
                    SUM(CASE WHEN A.SLA_BREACHED = TRUE THEN 1 ELSE 0 END) AS SLA_BREACHES,
                    SUM(
                        CASE
                            WHEN UPPER(COALESCE(A.RESOLUTION_CODE, '')) = 'FALSE_POSITIVE'
                              OR UPPER(A.STATUS) = 'CLOSED_FALSE'
                            THEN 1 ELSE 0
                        END
                    ) AS FALSE_POSITIVES,
                    SUM(
                        CASE
                            WHEN UPPER(COALESCE(A.RESOLUTION_CODE, '')) = 'TRUE_POSITIVE'
                              OR UPPER(A.STATUS) = 'CLOSED_TRUE'
                            THEN 1 ELSE 0
                        END
                    ) AS TRUE_POSITIVES,
                    SUM(CASE WHEN UPPER(A.STATUS) = 'CLOSED_FALSE' THEN 1 ELSE 0 END) AS REVIEW_TIMEOUTS
                FROM {schema}.RISK_ALERTS A
                LEFT JOIN {schema}.TRANSACTIONS T ON T.TRANSACTION_ID = A.TRANSACTION_ID
                WHERE A.CREATED_AT >= ADD_MONTHS(CURRENT_DATE, -11)
                GROUP BY TO_VARCHAR(A.CREATED_AT, 'YYYY-MM')
                ORDER BY MONTH DESC
                LIMIT 12
            ) RECENT
            ORDER BY MONTH ASC
        """
        monthly_rows = self.hana.query(monthly_sql)
        review_hours_by_month = self._load_audit_median_review_hours(team_schema)

        months: list[dict] = []
        for row in monthly_rows:
            month = str(row.get("month"))
            months.append(
                {
                    "month": month,
                    "raised": int(row.get("raised") or 0),
                    "closed": int(row.get("closed") or 0),
                    "transaction_value_usd": float(row.get("transaction_value_usd") or 0),
                    "sla_breaches": int(row.get("sla_breaches") or 0),
                    "false_positives": int(row.get("false_positives") or 0),
                    "true_positives": int(row.get("true_positives") or 0),
                    "median_review_hours": review_hours_by_month.get(month),
                }
            )

        # Ensure a contiguous 12-month window even if some months have zero alerts.
        months = self._fill_month_gaps(months, 12)

        totals_sql = f"""
            SELECT
                COUNT(*) AS TOTAL_ALERTS,
                SUM(CASE WHEN UPPER(STATUS) LIKE 'CLOSED%' THEN 1 ELSE 0 END) AS CLOSED_ALERTS,
                SUM(CASE WHEN UPPER(STATUS) = 'CLOSED_FALSE' THEN 1 ELSE 0 END) AS TIMEOUT_ALERTS,
                SUM(CASE WHEN SLA_BREACHED = TRUE THEN 1 ELSE 0 END) AS SLA_BREACHES,
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(RESOLUTION_CODE, '')) = 'FALSE_POSITIVE'
                          OR UPPER(STATUS) = 'CLOSED_FALSE'
                        THEN 1 ELSE 0
                    END
                ) AS FALSE_POSITIVES,
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(RESOLUTION_CODE, '')) = 'TRUE_POSITIVE'
                          OR UPPER(STATUS) = 'CLOSED_TRUE'
                        THEN 1 ELSE 0
                    END
                ) AS TRUE_POSITIVES
            FROM {schema}.RISK_ALERTS
            WHERE CREATED_AT >= ADD_MONTHS(CURRENT_DATE, -11)
        """
        totals = self.hana.query(totals_sql)[0]
        period_raised = int(totals.get("total_alerts") or 0)
        period_closed = int(totals.get("closed_alerts") or 0)
        period_fp = int(totals.get("false_positives") or 0)
        period_tp = int(totals.get("true_positives") or 0)
        period_sla = int(totals.get("sla_breaches") or 0)
        timeouts = int(totals.get("timeout_alerts") or 0)
        latest = months[-1] if months else {"raised": 0, "closed": 0}
        median_values = [point["median_review_hours"] for point in months if point.get("median_review_hours") is not None]
        overall_median = median_values[-1] if median_values else None

        return {
            "data_mode": "hana",
            "months": months,
            "kpis": {
                "backlog": 0,
                "open_alerts": 0,
                "investigating": 0,
                "median_review_hours": overall_median,
                "closure_rate": round(period_closed / period_raised, 3) if period_raised else 0.0,
                "sla_adherence_rate": round(1 - (period_sla / period_raised), 3) if period_raised else 0.0,
                "false_positive_rate": round(period_fp / (period_fp + period_tp), 3) if (period_fp + period_tp) else 0.0,
                "review_timeout_rate": round(timeouts / period_raised, 3) if period_raised else 0.0,
                "high_priority_unresolved": 0,
                "high_priority_exposure_usd": 0.0,
                "unresolved_exposure_usd": 0.0,
                "backlog_change": int(latest.get("raised") or 0) - int(latest.get("closed") or 0),
                "period_raised": period_raised,
                "period_closed": period_closed,
                "scored_queue_size": 0,
            },
            "notes": [
                "Closed outcomes are grouped by alert created month because RESOLVED_AT is not reliable for trends.",
                "Median review hours are derived from TEAM_08.AUDIT_LOG workflow timestamps when available.",
                "Client-reported AML false-positive baseline is 90–95%; chart shows dataset resolution outcomes.",
            ],
        }

    def _load_audit_median_review_hours(self, team_schema: str) -> dict[str, float]:
        """Median hours from first review action to close/SAR action, by alert created month."""
        try:
            rows = self.hana.query(
                f"""
                SELECT
                    TO_VARCHAR(A.CREATED_AT, 'YYYY-MM') AS MONTH,
                    SECONDS_BETWEEN(MIN(R.ACTION_TIMESTAMP), MAX(C.ACTION_TIMESTAMP)) / 3600.0 AS REVIEW_HOURS
                FROM {self.settings.reference_schema}.RISK_ALERTS A
                JOIN {team_schema}.AUDIT_LOG R
                  ON R.ENTITY_ID = TO_VARCHAR(A.ALERT_ID)
                 AND UPPER(R.ACTION_TYPE) IN ('REVIEW_ALERT', 'OPEN_CASE')
                JOIN {team_schema}.AUDIT_LOG C
                  ON C.ENTITY_ID = TO_VARCHAR(A.ALERT_ID)
                 AND UPPER(C.ACTION_TYPE) IN ('CLOSE_CASE', 'FILE_SAR', 'DECLINE_SAR', 'ESCALATE_ALERT')
                 AND C.ACTION_TIMESTAMP >= R.ACTION_TIMESTAMP
                WHERE A.CREATED_AT >= ADD_MONTHS(CURRENT_DATE, -11)
                GROUP BY A.ALERT_ID, TO_VARCHAR(A.CREATED_AT, 'YYYY-MM')
                """
            )
        except Exception as exc:
            logger.warning("Audit-log review duration query unavailable: %s", exc)
            return {}

        buckets: dict[str, list[float]] = {}
        for row in rows:
            month = str(row.get("month"))
            hours = row.get("review_hours")
            if hours is None:
                continue
            try:
                value = float(hours)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
            buckets.setdefault(month, []).append(value)

        medians: dict[str, float] = {}
        for month, values in buckets.items():
            values.sort()
            mid = len(values) // 2
            if not values:
                continue
            if len(values) % 2:
                medians[month] = round(values[mid], 1)
            else:
                medians[month] = round((values[mid - 1] + values[mid]) / 2, 1)
        return medians

    @staticmethod
    def _fill_month_gaps(months: list[dict], count: int = 12) -> list[dict]:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        keyed = {str(item["month"]): item for item in months}
        filled: list[dict] = []
        year, month = now.year, now.month
        for offset in range(count - 1, -1, -1):
            m = month - offset
            y = year
            while m <= 0:
                m += 12
                y -= 1
            key = f"{y:04d}-{m:02d}"
            filled.append(
                keyed.get(
                    key,
                    {
                        "month": key,
                        "raised": 0,
                        "closed": 0,
                        "transaction_value_usd": 0.0,
                        "sla_breaches": 0,
                        "false_positives": 0,
                        "true_positives": 0,
                        "median_review_hours": None,
                    },
                )
            )
        return filled

    def get_score(self, alert_id: str) -> RiskScore | None:
        return self._scores.get(alert_id)

    def save_score(self, score: RiskScore) -> None:
        with self._lock:
            self._scores[score.alert_id] = score

    def get_explanation(self, alert_id: str) -> Explanation | None:
        return self._explanations.get(alert_id)

    def save_explanation(self, explanation: Explanation) -> None:
        with self._lock:
            self._explanations[explanation.alert_id] = explanation

    def get_insight(self, alert_id: str) -> ActionableInsight | None:
        return self._insights.get(alert_id)

    def get_insight_by_id(self, insight_id: str) -> ActionableInsight | None:
        return next((item for item in self._insights.values() if item.insight_id == insight_id), None)

    def save_insight(self, insight: ActionableInsight) -> None:
        with self._lock:
            self._insights[insight.alert_id] = insight

    def append_insight_decision(self, record: InsightDecisionRecord) -> None:
        with self._lock:
            self._insight_audit_log.append(record)
            self._persist_audit_event(
                {
                    "event_type": "insight_decision",
                    "payload": record.model_dump(mode="json"),
                }
            )

    def list_insight_decisions(self, alert_id: str | None = None) -> list[InsightDecisionRecord]:
        if alert_id is None:
            return list(self._insight_audit_log)
        return [item for item in self._insight_audit_log if item.alert_id == alert_id]

    def get_chat_thread(self, alert_id: str) -> list[ChatMessage]:
        return list(self._chat_threads.get(alert_id, []))

    def append_chat_messages(self, alert_id: str, messages: list[ChatMessage]) -> None:
        with self._lock:
            thread = self._chat_threads.setdefault(alert_id, [])
            thread.extend(messages)

    def append_chat_audit(self, record: ChatAuditRecord) -> None:
        with self._lock:
            self._chat_audit_log.append(record)
            self._persist_audit_event(
                {
                    "event_type": "case_chat",
                    "payload": record.model_dump(mode="json"),
                }
            )

    def list_chat_audit(self, alert_id: str | None = None) -> list[ChatAuditRecord]:
        if alert_id is None:
            return list(self._chat_audit_log)
        return [item for item in self._chat_audit_log if item.alert_id == alert_id]

    def get_performance_chat_thread(self, thread_id: str) -> list[ChatMessage]:
        return list(self._performance_chat_threads.get(thread_id, []))

    def append_performance_chat_messages(self, thread_id: str, messages: list[ChatMessage]) -> None:
        with self._lock:
            thread = self._performance_chat_threads.setdefault(thread_id, [])
            thread.extend(messages)

    def append_performance_chat_audit(self, record: PerformanceChatAuditRecord) -> None:
        with self._lock:
            self._performance_chat_audit_log.append(record)
            self._persist_audit_event(
                {
                    "event_type": "performance_chat",
                    "payload": record.model_dump(mode="json"),
                }
            )

    def list_performance_chat_audit(self, thread_id: str | None = None) -> list[PerformanceChatAuditRecord]:
        if thread_id is None:
            return list(self._performance_chat_audit_log)
        return [item for item in self._performance_chat_audit_log if item.thread_id == thread_id]

    def list_audit_events(self, *, alert_id: str | None = None, limit: int = 50) -> list[AuditEvent]:
        events: list[AuditEvent] = []
        for record in self._insight_audit_log:
            events.append(
                AuditEvent(
                    event_type="insight_decision",
                    timestamp=record.decided_at,
                    alert_id=record.alert_id,
                    actor=record.actor,
                    summary=f"Decision {record.decision} → {record.resulting_status}",
                    refused_action=False,
                    detail={
                        "insight_id": record.insight_id,
                        "decision": record.decision,
                        "reason_code": record.reason_code,
                        "previous_status": record.previous_status,
                        "resulting_status": record.resulting_status,
                    },
                )
            )
        for record in self._chat_audit_log:
            events.append(
                AuditEvent(
                    event_type="case_chat",
                    timestamp=record.created_at,
                    alert_id=record.alert_id,
                    actor=record.actor,
                    summary=(
                        "Case chat action refused"
                        if record.refused_action
                        else "Case chat turn recorded"
                    ),
                    refused_action=record.refused_action,
                    detail={
                        "turn_id": record.turn_id,
                        "user_message": record.user_message[:160],
                        "chart_type": record.chart_type,
                    },
                )
            )
        for record in self._performance_chat_audit_log:
            events.append(
                AuditEvent(
                    event_type="performance_chat",
                    timestamp=record.created_at,
                    alert_id=None,
                    actor=record.actor,
                    summary=(
                        "Performance chat action refused"
                        if record.refused_action
                        else "Performance chat turn recorded"
                    ),
                    refused_action=record.refused_action,
                    detail={
                        "turn_id": record.turn_id,
                        "thread_id": record.thread_id,
                        "range_months": record.range_months,
                        "user_message": record.user_message[:160],
                    },
                )
            )
        if alert_id:
            events = [event for event in events if event.alert_id == alert_id]
        events.sort(key=lambda item: item.timestamp, reverse=True)
        return events[: max(1, min(limit, 200))]

    def _persist_audit_event(self, envelope: dict) -> None:
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(envelope, default=str) + "\n")
        except OSError as exc:
            logger.warning("Could not persist audit event: %s", exc)

    def _load_audit_from_disk(self) -> None:
        path = self._audit_path
        if not path.exists():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("Could not load audit log: %s", exc)
            return
        for line in lines[-AUDIT_LOAD_LIMIT:]:
            line = line.strip()
            if not line:
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = envelope.get("event_type")
            payload = envelope.get("payload") or {}
            try:
                if event_type == "insight_decision":
                    self._insight_audit_log.append(InsightDecisionRecord.model_validate(payload))
                elif event_type == "case_chat":
                    self._chat_audit_log.append(ChatAuditRecord.model_validate(payload))
                elif event_type == "performance_chat":
                    self._performance_chat_audit_log.append(
                        PerformanceChatAuditRecord.model_validate(payload)
                    )
            except Exception as exc:
                logger.debug("Skipping corrupt audit row: %s", exc)
