from __future__ import annotations

from typing import Any

from app.models.schemas import PrecedentCase, RoutingSuggestion

# Shared mock case-evidence store for Actionable Insights and Case Assistant.
CASE_EVIDENCE: dict[str, dict[str, Any]] = {
    "ALT-2026-00841": {
        "counterparty_history": "Al Noor Commodities FZE appeared on 2 prior high-value corridors in 18 months.",
        "prior_alerts": 3,
        "transaction_metadata": "SWIFT MT103; newly disclosed beneficial owner within 30 days.",
        "sanctions_list_version": "OFAC SDN 2026-07-15 + MAS Terrorism List v4.2",
        "related_transactions": [
            {"id": "TXN-882090", "amount": 1_200_000, "currency": "USD", "days_before": 2, "purpose": "Advance settlement"},
            {"id": "TXN-882098", "amount": 980_000, "currency": "USD", "days_before": 1, "purpose": "Partial trade settlement"},
            {"id": "TXN-882104", "amount": 4_850_000, "currency": "USD", "days_before": 0, "purpose": "Trade settlement"},
        ],
        "prior_alert_summaries": [
            {"id": "ALT-2025-01402", "type": "Rapid movement", "outcome": "Escalated Tier-2", "year": 2025},
            {"id": "ALT-2025-00911", "type": "Sanctions screening", "outcome": "Cleared after alias check", "year": 2025},
            {"id": "ALT-2024-02155", "type": "High-value threshold", "outcome": "SAR drafted", "year": 2024},
        ],
        "precedents": [
            PrecedentCase(
                pattern="Sanctions hit + rapid multi-leg movement",
                similar_count=14,
                escalated_to_sar_pct=71.0,
                typical_outcome="Escalated; SAR drafted after Tier-2 review",
            ),
            PrecedentCase(
                pattern="High-risk destination with PEP association",
                similar_count=9,
                escalated_to_sar_pct=56.0,
                typical_outcome="Additional KYC then Tier-2 escalation",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2025-4412",
                "pattern": "Sanctions hit + rapid multi-leg movement",
                "outcome": "SAR filed",
                "disposition": "draft_sar",
                "year": 2025,
                "notes": "Three linked SWIFT legs within 48h; list match confirmed on secondary alias.",
            },
            {
                "case_id": "CASE-2024-3188",
                "pattern": "High-risk destination with PEP association",
                "outcome": "Escalated Tier-2; KYC refresh",
                "disposition": "escalate_tier2",
                "year": 2024,
                "notes": "PEP link via beneficial owner; no SAR after source-of-funds attestation.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-2 Sanctions Desk",
            queue="SAR-CANDIDATE-APAC",
            jurisdiction="SG",
            workload_note="Mocked queue depth: 7 open (above weekly average of 4)",
        ),
    },
    "ALT-2026-00839": {
        "counterparty_history": "Bosphorus Machinery AS has 1 prior near-threshold transfer cluster.",
        "prior_alerts": 1,
        "transaction_metadata": "Three SEPA credits within 2% of internal review threshold.",
        "sanctions_list_version": "EU Consolidated List 2026-06-30",
        "related_transactions": [
            {"id": "TXN-882071", "amount": 975_000, "currency": "EUR", "days_before": 3, "purpose": "Equipment deposit"},
            {"id": "TXN-882074", "amount": 982_000, "currency": "EUR", "days_before": 2, "purpose": "Equipment balance"},
            {"id": "TXN-882077", "amount": 987_500, "currency": "EUR", "days_before": 0, "purpose": "Equipment purchase"},
        ],
        "prior_alert_summaries": [
            {"id": "ALT-2025-00660", "type": "Structuring pattern", "outcome": "Cleared after KYC", "year": 2025},
        ],
        "precedents": [
            PrecedentCase(
                pattern="Structuring just below threshold",
                similar_count=22,
                escalated_to_sar_pct=18.0,
                typical_outcome="Tier-2 pattern review; often cleared after KYC refresh",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2025-2201",
                "pattern": "Structuring just below threshold",
                "outcome": "Cleared after KYC refresh",
                "disposition": "clear",
                "year": 2025,
                "notes": "Three near-threshold SEPA credits; commercial invoices corroborated.",
            },
            {
                "case_id": "CASE-2024-1877",
                "pattern": "Structuring just below threshold",
                "outcome": "Escalated Tier-2",
                "disposition": "escalate_tier2",
                "year": 2024,
                "notes": "No invoices on file; pattern repeated across two counterparties.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-1 EU Structuring",
            queue="PATTERN-REVIEW-EU",
            jurisdiction="DE",
            workload_note="Mocked queue depth: 11 open (moderate load)",
        ),
    },
    "ALT-2026-00836": {
        "counterparty_history": "Viet Delta Holdings JSC is a first-time counterparty for this client.",
        "prior_alerts": 1,
        "transaction_metadata": "New corridor; amount 4.47× baseline; ownership layers=3.",
        "sanctions_list_version": "OFAC SDN 2026-07-15",
        "related_transactions": [
            {"id": "TXN-882012", "amount": 2_300_000, "currency": "USD", "days_before": 0, "purpose": "Capital investment"},
        ],
        "prior_alert_summaries": [
            {"id": "ALT-2025-01120", "type": "Behavioural deviation", "outcome": "Request KYC", "year": 2025},
        ],
        "precedents": [
            PrecedentCase(
                pattern="New corridor + material baseline deviation",
                similar_count=17,
                escalated_to_sar_pct=24.0,
                typical_outcome="Request additional KYC/source-of-funds before disposition",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2025-3010",
                "pattern": "New corridor + material baseline deviation",
                "outcome": "Request additional KYC",
                "disposition": "request_kyc",
                "year": 2025,
                "notes": "First transfer to VN corridor; ownership layers incomplete at alert time.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-1 APAC KYC",
            queue="KYC-REFRESH-APAC",
            jurisdiction="SG",
            workload_note="Mocked queue depth: 5 open (below capacity)",
        ),
    },
    "ALT-2026-00831": {
        "counterparty_history": "Northern Grid Partners Inc is a recurring low-risk payee.",
        "prior_alerts": 0,
        "transaction_metadata": "Project financing; amount 1.28× baseline; low FATF corridor.",
        "sanctions_list_version": "EU Consolidated List 2026-06-30",
        "related_transactions": [
            {"id": "TXN-881941", "amount": 1_250_000, "currency": "EUR", "days_before": 0, "purpose": "Project financing"},
        ],
        "prior_alert_summaries": [],
        "precedents": [
            PrecedentCase(
                pattern="High-value threshold with low entity risk",
                similar_count=31,
                escalated_to_sar_pct=3.0,
                typical_outcome="Cleared after standard threshold attestation",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2025-0904",
                "pattern": "High-value threshold with low entity risk",
                "outcome": "Cleared",
                "disposition": "clear",
                "year": 2025,
                "notes": "Recurring project finance counterparty; baseline attestation on file.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-1 EU Threshold",
            queue="THRESHOLD-ATTEST-EU",
            jurisdiction="NL",
            workload_note="Mocked queue depth: 3 open (light load)",
        ),
    },
    "ALT-2026-00828": {
        "counterparty_history": "Nippon Cloud Systems KK has recurring licence settlements.",
        "prior_alerts": 0,
        "transaction_metadata": "Round-number SWIFT; amount 1.09× baseline.",
        "sanctions_list_version": "OFAC SDN 2026-07-15",
        "related_transactions": [
            {"id": "TXN-881903", "amount": 500_000, "currency": "USD", "days_before": 0, "purpose": "Software licence"},
        ],
        "prior_alert_summaries": [],
        "precedents": [
            PrecedentCase(
                pattern="Informational round-number alert",
                similar_count=40,
                escalated_to_sar_pct=1.0,
                typical_outcome="Cleared with brief narrative",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2026-0112",
                "pattern": "Informational round-number alert",
                "outcome": "Cleared",
                "disposition": "clear",
                "year": 2026,
                "notes": "Annual licence invoice matched; no entity red flags.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-1 APAC Standard",
            queue="STANDARD-REVIEW-APAC",
            jurisdiction="KR",
            workload_note="Mocked queue depth: 8 open (normal load)",
        ),
    },
    "ALT-2026-00822": {
        "counterparty_history": "Thames Custody Services plc is an established custody counterparty.",
        "prior_alerts": 0,
        "transaction_metadata": "Velocity above monthly baseline; amount near expected average.",
        "sanctions_list_version": "UK Sanctions List 2026-07-01",
        "related_transactions": [
            {"id": "TXN-881810", "amount": 740_000, "currency": "CAD", "days_before": 5, "purpose": "Custody settlement"},
            {"id": "TXN-881824", "amount": 780_000, "currency": "CAD", "days_before": 0, "purpose": "Custody settlement"},
        ],
        "prior_alert_summaries": [],
        "precedents": [
            PrecedentCase(
                pattern="Velocity threshold without entity red flags",
                similar_count=26,
                escalated_to_sar_pct=4.0,
                typical_outcome="Cleared after frequency attestation",
            ),
        ],
        "precedent_cases_detail": [
            {
                "case_id": "CASE-2025-1555",
                "pattern": "Velocity threshold without entity red flags",
                "outcome": "Cleared",
                "disposition": "clear",
                "year": 2025,
                "notes": "Month-end custody bunching; frequency attestation accepted.",
            },
        ],
        "routing": RoutingSuggestion(
            team="FCU Tier-1 NA Velocity",
            queue="VELOCITY-REVIEW-NA",
            jurisdiction="CA",
            workload_note="Mocked queue depth: 6 open (normal load)",
        ),
    },
}

DEFAULT_ROUTING = RoutingSuggestion(
    team="FCU Tier-1 General",
    queue="GENERAL-TRIAGE",
    jurisdiction="UN",
    workload_note="Mocked queue depth: 9 open (default routing)",
)


def get_case_evidence(alert_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    seeded = CASE_EVIDENCE.get(alert_id)
    if seeded:
        return seeded
    if context is None:
        return {
            "counterparty_history": "No counterparty history available.",
            "prior_alerts": 0,
            "transaction_metadata": "Not supplied.",
            "sanctions_list_version": "Not supplied",
            "related_transactions": [],
            "prior_alert_summaries": [],
            "precedents": [],
            "precedent_cases_detail": [],
            "routing": DEFAULT_ROUTING,
        }
    company = context["company"]
    signals = context.get("signals", {})
    return {
        "counterparty_history": f"Limited history for {context['transaction'].get('counterparty', 'counterparty')}.",
        "prior_alerts": int(company.get("prior_cases") or 0),
        "transaction_metadata": (
            f"{context['transaction'].get('channel', 'channel')}; "
            f"amount_ratio={float(signals.get('amount_ratio') or context.get('amount_ratio') or 1):.2f}."
        ),
        "sanctions_list_version": "Not supplied for this alert",
        "related_transactions": [],
        "prior_alert_summaries": [],
        "precedents": [
            PrecedentCase(
                pattern=str(context.get("alert_type") or "Similar alert pattern"),
                similar_count=max(1, int(company.get("prior_cases") or 0) + 3),
                escalated_to_sar_pct=12.0 if company.get("sanctions_match") else 8.0,
                typical_outcome="Human review with documented disposition",
            )
        ],
        "precedent_cases_detail": [],
        "routing": DEFAULT_ROUTING.model_copy(
            update={"jurisdiction": str(context.get("origin_country") or "UN")[:2].upper()}
        ),
    }
