from app.config import Settings
from app.models.schemas import PerformanceChatRequest
from app.services.ai_core_client import AICoreClient
from app.services.hana_client import HanaClient
from app.services.performance_chat import PerformanceChatService
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine


def build_perf_chat() -> tuple[RiskRepository, PerformanceChatService]:
    settings = Settings(data_mode="demo")
    repository = RiskRepository(settings, HanaClient(settings))
    scoring = ScoringEngine(settings, repository, AICoreClient(settings))
    chat = PerformanceChatService(settings, repository, scoring, AICoreClient(settings))
    return repository, chat


def test_thread_returns_three_suggestions_for_range() -> None:
    _, chat = build_perf_chat()
    thread = chat.get_thread(12)
    assert thread.range_months == 12
    assert len(thread.suggestions) == 3
    assert all(item.prompt for item in thread.suggestions)
    assert any(item.id == "chart_raised_closed" for item in thread.suggestions)
    assert "12-month" in thread.greeting


def test_six_month_scope_slices_months_and_recomputes_period_kpis() -> None:
    _, chat = build_perf_chat()
    full = chat._load_dashboard()
    scoped = chat._scope_dashboard(full, 6)
    assert len(scoped.months) == 6
    assert scoped.months == full.months[-6:]
    assert scoped.kpis.period_raised == sum(point.raised for point in scoped.months)
    assert scoped.kpis.period_closed == sum(point.closed for point in scoped.months)
    assert scoped.kpis.backlog == full.kpis.backlog


def test_chart_suggestion_returns_raised_vs_closed_points() -> None:
    repository, chat = build_perf_chat()
    response = chat.chat(
        PerformanceChatRequest(
            message="Chart raised versus closed cases for the last 12 months and explain backlog pressure.",
            range_months=12,
        )
    )
    assert response.chart is not None
    assert response.chart.chart_type == "raised_vs_closed"
    assert len(response.chart.points) == 12
    assert any(c.kind == "chart" for c in response.citations)
    assert repository.list_performance_chat_audit("PERF-12M")


def test_sla_question_cites_kpi_values() -> None:
    _, chat = build_perf_chat()
    response = chat.chat(
        PerformanceChatRequest(
            message="How is SLA adherence trending over the last 6 months? Cite the KPI and monthly figures.",
            range_months=6,
        )
    )
    assert response.range_months == 6
    assert response.reply
    assert any(c.kind in {"kpi", "definition", "chart"} for c in response.citations)
    if response.chart:
        assert len(response.chart.points) == 6
        assert response.chart.chart_type == "sla_breaches"


def test_action_and_forecast_requests_are_refused() -> None:
    repository, chat = build_perf_chat()
    action = chat.chat(
        PerformanceChatRequest(message="Please escalate the queue and clear these alerts now.")
    )
    assert action.refused_action is True
    assert "Approve" in action.reply or "Override" in action.reply or "command centre" in action.reply.lower()

    forecast = chat.chat(
        PerformanceChatRequest(message="Forecast next quarter's closure rate for me.")
    )
    assert forecast.refused_action is True
    assert "forecast" in forecast.reply.lower() or "can't" in forecast.reply.lower()
    assert repository.list_performance_chat_audit("PERF-12M")


def test_conversation_history_is_persisted_per_range() -> None:
    repository, chat = build_perf_chat()
    chat.chat(PerformanceChatRequest(message="What is the current backlog?", range_months=6))
    chat.chat(PerformanceChatRequest(message="And what is the closure rate?", range_months=6))
    thread_6 = repository.get_performance_chat_thread("PERF-6M")
    thread_12 = repository.get_performance_chat_thread("PERF-12M")
    assert len(thread_6) == 4
    assert len(thread_12) == 0
    hydrated = chat.get_thread(6)
    assert len(hydrated.messages) == 4


def test_backlog_fallback_includes_kpi_citations() -> None:
    _, chat = build_perf_chat()
    response = chat.chat(
        PerformanceChatRequest(
            message="Explain the current backlog and closure rate for this dashboard.",
            range_months=12,
        )
    )
    assert "backlog" in response.reply.lower()
    assert any(c.kind == "kpi" for c in response.citations)
    assert response.provenance in {"ai", "fallback"}
