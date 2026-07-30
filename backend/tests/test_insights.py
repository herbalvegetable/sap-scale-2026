from app.config import Settings
from app.services.actionable_insights import ActionableInsightsService
from app.services.ai_core_client import AICoreClient
from app.services.hana_client import HanaClient
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.models.schemas import InsightDecisionRequest


def build_insights() -> tuple[RiskRepository, ActionableInsightsService]:
    settings = Settings(data_mode="demo")
    repository = RiskRepository(settings, HanaClient(settings))
    scoring = ScoringEngine(settings, repository, AICoreClient(settings))
    insights = ActionableInsightsService(settings, repository, scoring, AICoreClient(settings))
    return repository, insights


def test_demo_alerts_map_to_distinct_actions() -> None:
    _, insights = build_insights()

    low_conf = insights.generate_insight("ALT-2026-00841", refresh=True)
    escalate = insights.generate_insight("ALT-2026-00839", refresh=True)
    kyc = insights.generate_insight("ALT-2026-00836", refresh=True)
    clear = insights.generate_insight("ALT-2026-00831", refresh=True)

    # Meridian would be draft_sar on rules alone, but low data confidence abstains to request_kyc
    assert low_conf.recommended_action == "request_kyc"
    assert low_conf.confidence == "low"
    assert escalate.recommended_action == "escalate_tier2"
    assert kyc.recommended_action == "request_kyc"
    assert clear.recommended_action == "clear"
    assert clear.confidence == "high"


def test_urgency_is_bounded_and_distinct_from_risk_total() -> None:
    _, insights = build_insights()
    insight = insights.generate_insight("ALT-2026-00841", refresh=True)

    assert 0 <= insight.urgency_score <= 100
    assert insight.urgency_breakdown
    assert abs(insight.urgency_score - sum(item.points for item in insight.urgency_breakdown)) < 0.2
    assert insight.reasoning_trace
    assert any(item.matched for item in insight.reasoning_trace)
    assert insight.draft_disclaimer.lower().startswith("draft")
    assert insight.provenance in {"rules+ai", "rules+fallback"}
    assert insight.confidence in {"high", "medium", "low"}


def test_decision_audit_appends_and_blocks_repeat() -> None:
    repository, insights = build_insights()
    insight = insights.generate_insight("ALT-2026-00828", refresh=True)
    assert insight.recommended_action == "clear"

    updated, record = insights.apply_decision(
        "ALT-2026-00828",
        InsightDecisionRequest(
            decision="overridden",
            reason_code="additional_context",
            free_text="Counterparty attestation already on file.",
            edited_draft_notes="Human-edited draft note.",
        ),
    )
    assert updated.status == "overridden"
    assert updated.draft_notes == "Human-edited draft note."
    assert record.framing == "decision_quality_audit"
    assert repository.list_insight_decisions("ALT-2026-00828")

    try:
        insights.apply_decision(
            "ALT-2026-00828",
            InsightDecisionRequest(decision="approved"),
        )
        raised = False
    except ValueError:
        raised = True
    assert raised
