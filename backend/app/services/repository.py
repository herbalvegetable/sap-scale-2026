from __future__ import annotations

import logging
from threading import Lock

from app.config import Settings
from app.models.schemas import Explanation, RiskScore
from app.services.demo_data import get_demo_alerts
from app.services.hana_client import HanaClient

logger = logging.getLogger(__name__)


class RiskRepository:
    """Repository facade with a visible, reliable demo fallback."""

    def __init__(self, settings: Settings, hana: HanaClient) -> None:
        self.settings = settings
        self.hana = hana
        self._scores: dict[str, RiskScore] = {}
        self._explanations: dict[str, Explanation] = {}
        self._contexts: list[dict] | None = None
        self._lock = Lock()
        self._mode: str | None = None

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
        return self._contexts

    def get_alert_context(self, alert_id: str) -> dict | None:
        return next((row for row in self.all_alert_contexts() if str(row["id"]) == alert_id), None)

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
                A.STATUS,
                A.ALERT_DESCRIPTION AS DESCRIPTION,
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
        return {
            **row,
            "id": str(row["id"]),
            "transaction_id": str(row["transaction_id"]),
            "company_id": str(row.get("company_id") or "UNKNOWN"),
            "company_name": str(row.get("company_name") or "Unknown entity"),
            "description": str(row.get("description") or row.get("alert_type") or "Transaction monitoring alert"),
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
        }

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
