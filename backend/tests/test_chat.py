from app.config import Settings
from app.models.schemas import ChatRequest
from app.services.ai_core_client import AICoreClient
from app.services.case_chat import CaseChatService
from app.services.hana_client import HanaClient
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore


def build_chat() -> tuple[RiskRepository, CaseChatService]:
    settings = Settings(data_mode="demo")
    repository = RiskRepository(settings, HanaClient(settings))
    scoring = ScoringEngine(settings, repository, AICoreClient(settings))
    vector = HanaVectorStore(settings, HanaClient(settings))
    chat = CaseChatService(settings, repository, scoring, AICoreClient(settings), vector)
    return repository, chat


def test_thread_returns_three_suggestions_including_chart() -> None:
    _, chat = build_chat()
    thread = chat.get_thread("ALT-2026-00841")
    assert len(thread.suggestions) == 3
    assert all(item.prompt for item in thread.suggestions)
    assert any(item.id == "chart_activity" for item in thread.suggestions)
    assert "ALT-2026-00841" in thread.greeting


def test_chart_suggestion_returns_activity_spec() -> None:
    repository, chat = build_chat()
    response = chat.chat(
        "ALT-2026-00841",
        ChatRequest(message="Chart this entity's recent transaction activity against its baseline."),
    )
    assert response.chart is not None
    assert response.chart.chart_type == "activity_vs_baseline"
    assert len(response.chart.points) >= 1
    assert any(c.kind == "chart" for c in response.citations)
    assert repository.list_chat_audit("ALT-2026-00841")


def test_action_request_is_refused_without_mutating_insight() -> None:
    repository, chat = build_chat()
    assert repository.get_insight("ALT-2026-00831") is None
    response = chat.chat("ALT-2026-00831", ChatRequest(message="Please escalate this alert for me now."))
    assert response.refused_action is True
    assert repository.get_insight("ALT-2026-00831") is None
    assert "Approve" in response.reply or "Override" in response.reply


def test_precedent_and_policy_fallbacks_cite_sources() -> None:
    _, chat = build_chat()
    precedent = chat.chat(
        "ALT-2026-00839",
        ChatRequest(message="Have we seen this pattern before? Show a similar past case and outcome."),
    )
    assert precedent.citations
    assert any(c.kind in {"precedent", "factor", "case_field"} for c in precedent.citations)

    policy = chat.chat(
        "ALT-2026-00836",
        ChatRequest(message="What policy or SLA applies given PEP and medium FATF on this alert?"),
    )
    assert policy.citations
    assert any(c.kind in {"policy", "factor", "case_field"} for c in policy.citations)


def test_why_factor_answer_includes_factor_citation() -> None:
    _, chat = build_chat()
    response = chat.chat(
        "ALT-2026-00828",
        ChatRequest(message="Why is entity_risk scored for this transaction? Cite the factor evidence."),
    )
    assert response.reply
    assert any(c.kind == "factor" for c in response.citations)
