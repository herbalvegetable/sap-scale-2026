from __future__ import annotations

import copy
import hashlib
import re
from typing import Any


SENSITIVE_NAME_KEYS = {
    "name",
    "company_name",
    "legal_name",
    "counterparty",
    "beneficiary_name",
    "owner_name",
    "resolved_by",
}
SENSITIVE_TEXT_KEYS = {
    "description",
    "purpose",
    "payment_purpose",
    "resolution_notes",
    "alert_description",
}
OWNER_PII_KEYS = {"nationality", "residence"}


def privacy_meta() -> dict[str, str]:
    return {
        "region": "AP-Southeast (Singapore BTP)",
        "mode": "prompt_minimisation",
    }


def _hash_token(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:4].upper()
    return f"{prefix}-{digest}"


def _redact_text(value: str, *, kind: str = "text") -> str:
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"not supplied", "unknown", "unknown entity", "unknown counterparty"}:
        return cleaned
    if kind == "company":
        return _hash_token(cleaned, "Company")
    if kind == "person":
        return _hash_token(cleaned, "Person")
    if kind == "purpose":
        if len(cleaned) <= 24:
            return "[redacted purpose]"
        return f"{cleaned[:18]}… [redacted purpose]"
    if len(cleaned) <= 40:
        return "[redacted]"
    return f"{cleaned[:24]}… [redacted]"


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    if not isinstance(value, str):
        return value
    if lowered in SENSITIVE_NAME_KEYS or lowered.endswith("_name"):
        if "company" in lowered or lowered in {"name", "legal_name"}:
            # Beneficial owner "name" treated as person; company_name as company.
            if lowered in {"name", "owner_name"} and "company" not in lowered:
                return _redact_text(value, kind="person")
            if lowered == "name":
                return _redact_text(value, kind="person")
            return _redact_text(value, kind="company")
        if lowered in {"counterparty", "beneficiary_name", "resolved_by"}:
            return _redact_text(value, kind="person")
        return _redact_text(value, kind="company")
    if lowered in SENSITIVE_TEXT_KEYS or lowered.endswith("_notes") or lowered.endswith("_description"):
        return _redact_text(value, kind="purpose" if "purpose" in lowered else "text")
    if lowered in OWNER_PII_KEYS:
        return "[redacted]"
    return value


def _redact_company(company: dict[str, Any], *, fallback_name: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in company.items():
        if key == "name" and isinstance(value, str):
            result[key] = _redact_text(value or fallback_name or "", kind="company")
        else:
            result[key] = _redact_value(key, value)
    if "name" not in result and fallback_name:
        result["name"] = _redact_text(fallback_name, kind="company")
    return result


def _redact_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    parent_company_name = payload.get("company_name") if isinstance(payload.get("company_name"), str) else None
    for key, value in payload.items():
        if key == "company" and isinstance(value, dict):
            result[key] = _redact_company(value, fallback_name=parent_company_name)
            continue
        if key == "beneficial_owners" and isinstance(value, list):
            result[key] = [_redact_owner(item) if isinstance(item, dict) else item for item in value]
            continue
        if key == "company_name" and isinstance(value, str):
            result[key] = _redact_text(value, kind="company")
            continue
        result[key] = _redact_value(key, value)
    if "company_name" in result and isinstance(result.get("company"), dict):
        company = dict(result["company"])
        company["name"] = result["company_name"]
        result["company"] = company
    return result


def _redact_owner(owner: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact_mapping(owner)
    if isinstance(redacted.get("name"), str):
        redacted["name"] = _redact_text(str(owner.get("name") or ""), kind="person")
    for key in OWNER_PII_KEYS:
        if key in redacted and isinstance(redacted[key], str):
            redacted[key] = "[redacted]"
    return redacted


def redact_for_llm(payload: Any) -> Any:
    """Return a deep-copied payload safe to send to an LLM (PII minimised)."""
    if payload is None:
        return None
    cloned = copy.deepcopy(payload)
    if isinstance(cloned, dict):
        redacted = _redact_mapping(cloned)
        redacted["_privacy"] = privacy_meta()
        return redacted
    if isinstance(cloned, list):
        return [redact_for_llm(item) for item in cloned]
    if isinstance(cloned, str):
        # Free-text blobs: mask email-like and long identifiers lightly.
        text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "[redacted-email]", cloned)
        return text
    return cloned
