from app.config import Settings
from app.services.ai_core_client import AICoreClient
from app.services.hana_client import HanaClient
from app.services.repository import RiskRepository
from app.services.scoring_engine import FACTOR_LIMITS, ScoringEngine


def build_engine() -> tuple[RiskRepository, ScoringEngine]:
    settings = Settings(data_mode="demo")
    repository = RiskRepository(settings, HanaClient(settings))
    return repository, ScoringEngine(settings, repository, AICoreClient(settings))


def test_fallback_score_is_bounded_and_complete() -> None:
    repository, engine = build_engine()
    alert_id = repository.all_alert_contexts()[0]["id"]

    result = engine.score_alert(alert_id)

    assert 0 <= result.total <= 100
    assert len(result.factors) == 5
    assert result.total == round(sum(item.score for item in result.factors), 1)
    assert result.provenance == "fallback"
    for factor in result.factors:
        assert factor.max_score == FACTOR_LIMITS[factor.key][1]
        assert 0 <= factor.score <= factor.max_score
        assert factor.rationale


def test_tier_boundaries() -> None:
    assert ScoringEngine.tier_for(0) == "low"
    assert ScoringEngine.tier_for(33) == "low"
    assert ScoringEngine.tier_for(34) == "medium"
    assert ScoringEngine.tier_for(66) == "medium"
    assert ScoringEngine.tier_for(67) == "high"
    assert ScoringEngine.tier_for(100) == "high"


def test_cached_score_has_cached_provenance() -> None:
    repository, engine = build_engine()
    alert_id = repository.all_alert_contexts()[0]["id"]

    first = engine.score_alert(alert_id, use_ai=False)
    second = engine.score_alert(alert_id, use_ai=False)

    assert first.total == second.total
    assert second.provenance == "cached"


def test_detail_path_does_not_change_list_score() -> None:
    """List uses fallback; detail must reuse that cache instead of silently AI-upgrading."""
    repository, engine = build_engine()
    alert_id = repository.all_alert_contexts()[0]["id"]

    list_score = engine.score_alert(alert_id, use_ai=False)
    detail_score = engine.score_alert(alert_id, use_ai=True)

    assert detail_score.total == list_score.total
    assert detail_score.tier == list_score.tier
    assert detail_score.provenance == "cached"
