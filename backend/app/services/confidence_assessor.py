"""Deterministic, rule-based confidence assessment for risk factors.

Confidence measures data-quality trustworthiness of inputs used to score a
factor. It does not change numeric factor scores or the 0–100 priority total.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.schemas import FactorConfidence, FactorScore, RiskScore

THRESHOLDS_PATH = Path(__file__).resolve().parent.parent / "confidence_thresholds.json"

LEVEL_RANK = {"high": 2, "medium": 1, "low": 0}
RANK_LEVEL = {2: "high", 1: "medium", 0: "low"}


@lru_cache(maxsize=1)
def load_thresholds() -> dict[str, Any]:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def _level_from_failures(fail_count: int, critical: bool) -> str:
    if critical or fail_count >= 2:
        return "low"
    if fail_count == 1:
        return "medium"
    return "high"


def _freshness_status(days: int | None, thresholds: dict[str, Any]) -> tuple[bool, bool, str]:
    """Return (failed, critical, reason_fragment)."""
    if days is None:
        return True, False, "reference data freshness is unknown"
    high_max = int(thresholds["freshness_high_max_days"])
    medium_max = int(thresholds["freshness_medium_max_days"])
    if days > medium_max:
        return True, True, f"reference data last refreshed {days} days ago (older than {medium_max} days)"
    if days > high_max:
        return True, False, f"reference data last refreshed {days} days ago (older than {high_max} days)"
    return False, False, f"reference data refreshed {days} days ago"


def _match_status(
    match_type: str,
    similarity: float | None,
    thresholds: dict[str, Any],
) -> tuple[bool, bool, str]:
    normalized = (match_type or "none").lower()
    if normalized in {"none", "exact", "confirmed", "id"}:
        return False, False, f"match certainty is {normalized}"
    if normalized in {"fuzzy", "name"}:
        floor = float(thresholds["match_fuzzy_min_similarity"])
        if similarity is not None and similarity < floor:
            return True, True, f"sanctions/name match is fuzzy ({similarity:.0f}% similarity), below {floor:.0f}% floor"
        if similarity is not None:
            return True, False, f"sanctions/name match is fuzzy ({similarity:.0f}% similarity), not an exact ID match"
        return True, False, "sanctions/name match is fuzzy, not an exact ID match"
    if normalized in {"unverified", "self_declared"}:
        return True, True, "screening or ownership data is unverified / self-declared"
    return True, False, f"match certainty is {normalized}"


def _corroboration_status(count: int, thresholds: dict[str, Any]) -> tuple[bool, bool, str]:
    minimum = int(thresholds["corroboration_high_min"])
    if count >= minimum:
        return False, False, f"{count} independent signals corroborate this factor"
    return True, False, f"only {count} independent signal(s); fewer than {minimum} required for high confidence"


def _completeness_status(
    factor_key: str,
    present: dict[str, bool],
    thresholds: dict[str, Any],
) -> tuple[bool, bool, str]:
    required = list(thresholds.get("factor_required_fields", {}).get(factor_key, []))
    missing = [field for field in required if not present.get(field, False)]
    if missing:
        critical = len(missing) >= max(1, len(required) // 2 + 1) or any(
            field in {"fatf_risk", "amount", "risk_rating"} for field in missing
        )
        return True, critical, f"required fields missing or unknown: {', '.join(missing)}"
    return False, False, "required factor inputs are populated"


def _signal_freshness(signals: dict[str, Any], key: str, thresholds: dict[str, Any]) -> int | None:
    if key in signals and signals[key] is not None:
        try:
            return int(signals[key])
        except (TypeError, ValueError):
            return None
    return int(thresholds["default_freshness_days"])


def _factor_inputs(factor: FactorScore, context: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    company = context.get("company") or {}
    signals = context.get("signals") or {}
    fatf = str(signals.get("fatf_risk") or "Unknown")
    amount_ratio = signals.get("amount_ratio")
    if amount_ratio is None:
        amount_ratio = context.get("amount_ratio")

    evidence_sources = {item.source for item in factor.evidence}
    corroboration = max(len(evidence_sources), len(factor.evidence))

    if factor.key == "entity_risk":
        match_type = str(signals.get("sanctions_match_type") or ("exact" if company.get("sanctions_match") else "none"))
        similarity = signals.get("sanctions_similarity")
        freshness = _signal_freshness(signals, "ownership_freshness_days", thresholds)
        if company.get("pep"):
            corroboration = max(corroboration, 2 if company.get("sanctions_match") else 1)
        present = {
            "risk_rating": bool(company.get("risk_rating")) and str(company.get("risk_rating")).lower() != "unknown",
            "sanctions_match": "sanctions_match" in company,
            "pep": "pep" in company,
        }
        return {
            "present": present,
            "match_type": match_type,
            "similarity": float(similarity) if similarity is not None else None,
            "freshness_days": freshness,
            "corroboration_count": corroboration + (1 if company.get("beneficial_owner_layers") else 0),
        }

    if factor.key == "transaction_behaviour":
        return {
            "present": {
                "amount": context.get("amount") is not None,
                "amount_ratio": amount_ratio is not None,
            },
            "match_type": "none",
            "similarity": None,
            "freshness_days": _signal_freshness(signals, "baseline_freshness_days", thresholds),
            "corroboration_count": corroboration
            + (1 if signals.get("rapid_transfers") is not None else 0)
            + (1 if amount_ratio is not None else 0),
        }

    if factor.key == "geographic_risk":
        known_fatf = fatf.lower() not in {"", "unknown", "none"}
        return {
            "present": {
                "destination_country": bool(context.get("destination_country")),
                "fatf_risk": known_fatf,
            },
            "match_type": "exact" if known_fatf else "unverified",
            "similarity": None,
            "freshness_days": _signal_freshness(signals, "country_data_freshness_days", thresholds),
            "corroboration_count": corroboration + (1 if signals.get("new_corridor") is not None else 0) + (1 if known_fatf else 0),
        }

    if factor.key == "behavioural_deviation":
        baseline = company.get("baseline_average_amount")
        return {
            "present": {
                "baseline_average_amount": baseline is not None and float(baseline or 0) > 0,
                "amount_ratio": amount_ratio is not None,
            },
            "match_type": "none",
            "similarity": None,
            "freshness_days": _signal_freshness(signals, "baseline_freshness_days", thresholds),
            "corroboration_count": corroboration
            + (1 if amount_ratio is not None else 0)
            + (1 if signals.get("new_corridor") is not None else 0),
        }

    # regulatory_sensitivity
    return {
        "present": {
            "prior_cases": company.get("prior_cases") is not None,
            "supervisory_attention": "supervisory_attention" in signals,
        },
        "match_type": "none",
        "similarity": None,
        "freshness_days": _signal_freshness(signals, "cases_freshness_days", thresholds),
        "corroboration_count": corroboration
        + (1 if company.get("prior_cases") is not None else 0)
        + (1 if "supervisory_attention" in signals else 0),
    }


def assess_factor_confidence(factor: FactorScore, context: dict[str, Any]) -> FactorConfidence:
    thresholds = load_thresholds()
    extracted = _factor_inputs(factor, context, thresholds)
    reasons: list[str] = []
    fail_count = 0
    critical = False

    complete_fail, complete_critical, complete_note = _completeness_status(
        factor.key, extracted["present"], thresholds
    )
    if complete_fail:
        fail_count += 1
        critical = critical or complete_critical
        reasons.append(complete_note)
    else:
        reasons.append(complete_note)

    match_fail, match_critical, match_note = _match_status(
        extracted["match_type"], extracted["similarity"], thresholds
    )
    # Match certainty only counts as a failure path for factors that use screening matches.
    if factor.key in {"entity_risk", "geographic_risk"}:
        if match_fail:
            fail_count += 1
            critical = critical or match_critical
            reasons.append(match_note)
        else:
            reasons.append(match_note)
    else:
        reasons.append("match certainty is not applicable to this factor")

    fresh_fail, fresh_critical, fresh_note = _freshness_status(extracted["freshness_days"], thresholds)
    if fresh_fail:
        fail_count += 1
        critical = critical or fresh_critical
        reasons.append(fresh_note)
    else:
        reasons.append(fresh_note)

    corr_fail, corr_critical, corr_note = _corroboration_status(
        int(extracted["corroboration_count"]), thresholds
    )
    if corr_fail:
        fail_count += 1
        critical = critical or corr_critical
        reasons.append(corr_note)
    else:
        reasons.append(corr_note)

    level = _level_from_failures(fail_count, critical)
    # Surface only failure reasons when not high; keep at least one positive note when high.
    if level == "high":
        display_reasons = ["All confidence inputs meet high-confidence thresholds for this factor."]
    else:
        display_reasons = [
            note
            for note, failed in (
                (complete_note, complete_fail),
                (match_note, match_fail and factor.key in {"entity_risk", "geographic_risk"}),
                (fresh_note, fresh_fail),
                (corr_note, corr_fail),
            )
            if failed
        ]
        if not display_reasons:
            display_reasons = reasons[:2]

    return FactorConfidence(
        level=level,  # type: ignore[arg-type]
        reasons=display_reasons,
        inputs={
            "data_completeness": "complete" if not complete_fail else "incomplete",
            "match_certainty": extracted["match_type"],
            "data_freshness_days": extracted["freshness_days"]
            if extracted["freshness_days"] is not None
            else "unknown",
            "corroboration_count": int(extracted["corroboration_count"]),
            "fail_count": fail_count,
            "critical_failure": critical,
        },
    )


def key_driving_factors(factors: list[FactorScore], thresholds: dict[str, Any] | None = None) -> list[FactorScore]:
    cfg = thresholds or load_thresholds()
    ratio_threshold = float(cfg["key_driver_ratio_threshold"])
    fallback_count = int(cfg["key_driver_fallback_count"])
    ranked = sorted(
        factors,
        key=lambda item: (item.score / item.max_score) if item.max_score else 0,
        reverse=True,
    )
    drivers = [factor for factor in ranked if factor.max_score and (factor.score / factor.max_score) >= ratio_threshold]
    if not drivers:
        drivers = ranked[:fallback_count]
    return drivers


def rollup_confidence(factors: list[FactorScore]) -> FactorConfidence:
    drivers = key_driving_factors(factors)
    if not drivers:
        return FactorConfidence(
            level="medium",
            reasons=["No scored factors were available to assess confidence."],
            inputs={"key_driver_count": 0},
        )

    lowest_rank = min(LEVEL_RANK.get(factor.confidence.level, 1) for factor in drivers)
    level = RANK_LEVEL[lowest_rank]
    reasons: list[str] = []
    for factor in drivers:
        if LEVEL_RANK.get(factor.confidence.level, 1) <= lowest_rank:
            for reason in factor.confidence.reasons:
                labeled = f"{factor.label}: {reason}"
                if labeled not in reasons:
                    reasons.append(labeled)
    if level == "high":
        reasons = [
            f"Key driving factors ({', '.join(f.label for f in drivers)}) all meet high-confidence data-quality thresholds."
        ]
    return FactorConfidence(
        level=level,  # type: ignore[arg-type]
        reasons=reasons[:4],
        inputs={
            "key_drivers": [factor.key for factor in drivers],
            "key_driver_levels": {factor.key: factor.confidence.level for factor in drivers},
            "rollup_rule": "floor_of_key_drivers",
        },
    )


def attach_confidence(factors: list[FactorScore], context: dict[str, Any]) -> tuple[list[FactorScore], FactorConfidence]:
    enriched: list[FactorScore] = []
    for factor in factors:
        confidence = assess_factor_confidence(factor, context)
        enriched.append(factor.model_copy(update={"confidence": confidence}))
    return enriched, rollup_confidence(enriched)


def targeted_investigator_checks(score: RiskScore) -> list[str]:
    """Generate targeted checks from low-confidence key drivers (deterministic text)."""
    checks: list[str] = []
    for factor in key_driving_factors(score.factors):
        if factor.confidence.level != "low":
            continue
        for reason in factor.confidence.reasons:
            if factor.key == "entity_risk" and ("fuzzy" in reason.lower() or "sanctions" in reason.lower() or "unverified" in reason.lower()):
                checks.append(f"Verify sanctions/PEP screening before escalating - {reason}")
            elif factor.key == "geographic_risk":
                checks.append(f"Confirm destination country risk classification - {reason}")
            elif factor.key == "behavioural_deviation":
                checks.append(f"Re-validate transaction baseline before relying on deviation scoring - {reason}")
            elif factor.key == "transaction_behaviour":
                checks.append(f"Confirm transaction amount and related-transfer evidence - {reason}")
            elif factor.key == "regulatory_sensitivity":
                checks.append(f"Review prior compliance cases and supervisory context - {reason}")
            else:
                checks.append(f"Investigate data quality for {factor.label.lower()} - {reason}")
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for check in checks:
        if check not in seen:
            seen.add(check)
            unique.append(check)
    return unique
