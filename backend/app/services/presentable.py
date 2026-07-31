"""Helpers to keep user-facing copy in plain English (no raw codes)."""

from __future__ import annotations

from typing import Any

ACTION_LABELS: dict[str, str] = {
    "clear": "Clear",
    "escalate_tier2": "Escalate to Tier 2",
    "request_kyc": "Request Additional KYC/Info",
    "draft_sar": "Draft SAR",
}

FACTOR_LABELS: dict[str, str] = {
    "entity_risk": "Entity risk profile",
    "transaction_behaviour": "Transaction behaviour",
    "geographic_risk": "Geographic risk",
    "behavioural_deviation": "Behavioural deviation",
    "regulatory_sensitivity": "Regulatory sensitivity",
}

FIELD_LABELS: dict[str, str] = {
    "fatf_risk": "destination country risk",
    "amount_ratio": "amount versus baseline",
    "risk_rating": "entity risk rating",
    "sanctions_match": "sanctions screening",
    "pep": "PEP association",
    "prior_cases": "prior compliance cases",
    "beneficial_owner_layers": "beneficial ownership layers",
    "new_corridor": "new corridor flag",
    "amount": "transaction amount",
    "ownership_freshness_days": "ownership data freshness",
    "sanctions_match_type": "sanctions match type",
    "sanctions_similarity": "sanctions similarity",
    "supervisory_attention": "supervisory attention",
    "rapid_transfers": "rapid related transfers",
    "baseline_average_amount": "baseline average amount",
    "entity_risk": "entity risk profile",
    "geographic_risk": "geographic risk",
    "regulatory_sensitivity": "regulatory sensitivity",
    "transaction_behaviour": "transaction behaviour",
    "behavioural_deviation": "behavioural deviation",
    "incomplete_evidence": "incomplete evidence",
    "tier": "risk tier",
}

SOURCE_LABELS: dict[str, str] = {
    "COMPANY_RISK_PROFILES": "Company risk profiles",
    "COMPANY": "Company screening",
    "TRANSACTIONS": "Transaction records",
    "COUNTRIES": "Country risk data",
    "TRANSACTION_BASELINES": "Transaction baselines",
    "COMPLIANCE_CASES": "Compliance case history",
    "TRANSACTION activity + TRANSACTION_BASELINES": "Transaction activity and baselines",
    "Mock case-data store": "Case evidence store",
    "Mock case-data store (precedent cases)": "Precedent case evidence",
    "RiskAssess scoring engine": "RiskAssess scoring",
    "RiskAssess factor evidence": "Risk factor evidence",
    "COMPANY screening flags": "Company screening",
}

STATUS_LABELS: dict[str, str] = {
    "generated": "Generated",
    "reviewed": "Reviewed",
    "approved": "Approved",
    "overridden": "Declined",
    "actioned": "Actioned",
    "further_info_requested": "Further information requested",
    "open": "Open",
    "investigating": "Investigating",
    "closed": "Closed",
    "closed_timeout": "Closed – Closed due to expired review timeline",
}

TIER_LABELS: dict[str, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

CONFIDENCE_LABELS: dict[str, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

QUEUE_LABELS: dict[str, str] = {
    "SAR-CANDIDATE-APAC": "SAR candidate — Asia Pacific",
    "PATTERN-REVIEW-EU": "Pattern review — Europe",
    "KYC-REFRESH-APAC": "KYC refresh — Asia Pacific",
    "THRESHOLD-ATTEST-EU": "Threshold attestation — Europe",
    "STANDARD-REVIEW-APAC": "Standard review — Asia Pacific",
    "VELOCITY-REVIEW-NA": "Velocity review — North America",
    "GENERAL-TRIAGE": "General triage",
}

RULE_LABELS: dict[str, str] = {
    "SAR-01": "Sanctions / high-risk SAR path",
    "ESC-01": "Tier-2 escalation path",
    "KYC-01": "Additional KYC path",
    "CLR-01": "Clearance path",
    "KYC-DEFAULT": "Default KYC path",
    "CONF-ABSTAIN-01": "Low-confidence abstention",
}

ACRONYMS = {"SLA", "KYC", "PEP", "SAR", "FATF", "OFAC", "EU", "UK", "USD", "EUR", "CAD", "APAC", "NA", "GCRO", "FCU"}


def yes_no(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def action_label(value: str | None) -> str:
    if not value:
        return "Continued review"
    return ACTION_LABELS.get(value, humanize_code(value))


def factor_label(value: str | None) -> str:
    if not value:
        return "Risk factor"
    return FACTOR_LABELS.get(value, humanize_code(value))


def field_label(value: str | None) -> str:
    if not value:
        return "field"
    return FIELD_LABELS.get(value, humanize_code(value).lower())


def source_label(value: str | None) -> str:
    if not value:
        return "Case evidence"
    return SOURCE_LABELS.get(value, humanize_code(value))


def status_label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return STATUS_LABELS.get(value, humanize_code(value))


def tier_label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return TIER_LABELS.get(str(value).lower(), humanize_code(str(value)))


def confidence_label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return CONFIDENCE_LABELS.get(str(value).lower(), humanize_code(str(value)))


def queue_label(value: str | None) -> str:
    if not value:
        return "General triage"
    return QUEUE_LABELS.get(value, humanize_code(value))


def rule_label(value: str | None) -> str:
    if not value:
        return "Rule"
    return RULE_LABELS.get(value, humanize_code(value))


def humanize_code(value: str) -> str:
    text = (
        str(value)
        .replace("+", " ")
        .replace("=", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    parts = []
    for raw in text.replace("/", " ").replace("_", " ").replace("-", " ").replace(".", " ").split():
        upper = raw.upper()
        if upper in ACRONYMS:
            parts.append(upper)
        elif raw.isdigit():
            parts.append(raw)
        else:
            parts.append(raw[:1].upper() + raw[1:].lower())
    return " ".join(parts) if parts else str(value)


def present_missing_fields(fields: list[str]) -> str:
    labels = [field_label(field) for field in fields]
    if not labels:
        return "required inputs are missing"
    if len(labels) == 1:
        return f"required input missing or unknown: {labels[0]}"
    return f"required inputs missing or unknown: {', '.join(labels[:-1])}, and {labels[-1]}"
