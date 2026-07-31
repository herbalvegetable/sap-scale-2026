from app.config import Settings
from app.services.demo_analytics import build_demo_operations_dashboard
from app.services.hana_client import HanaClient
from app.services.repository import RiskRepository
from fastapi.testclient import TestClient

from app.dependencies import (
    get_case_chat_service,
    get_insights_service,
    get_repository,
    get_scoring_engine,
    get_vector_store,
)
from app.main import app
from app.services.actionable_insights import ActionableInsightsService
from app.services.ai_core_client import AICoreClient
from app.services.case_chat import CaseChatService
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore


settings = Settings(data_mode="demo")
repository = RiskRepository(settings, HanaClient(settings))
scoring = ScoringEngine(settings, repository, AICoreClient(settings))
insights = ActionableInsightsService(settings, repository, scoring, AICoreClient(settings))
vector = HanaVectorStore(settings, HanaClient(settings))
chat = CaseChatService(settings, repository, scoring, AICoreClient(settings), vector)
app.dependency_overrides[get_repository] = lambda: repository
app.dependency_overrides[get_scoring_engine] = lambda: scoring
app.dependency_overrides[get_insights_service] = lambda: insights
app.dependency_overrides[get_vector_store] = lambda: vector
app.dependency_overrides[get_case_chat_service] = lambda: chat
client = TestClient(app)


def test_demo_operations_series_shape() -> None:
    payload = build_demo_operations_dashboard()
    months = payload["months"]
    assert len(months) == 12
    assert months == sorted(months, key=lambda item: item["month"])
    for point in months:
        assert point["raised"] >= 0
        assert point["closed"] >= 0
        assert point["transaction_value_usd"] >= 0
        assert point["sla_breaches"] >= 0
        assert point["false_positives"] + point["true_positives"] == point["closed"]
        assert point["median_review_hours"] is not None
    kpis = payload["kpis"]
    assert 0 <= kpis["closure_rate"] <= 1.5
    assert 0 <= kpis["false_positive_rate"] <= 1
    assert 0 <= kpis["review_timeout_rate"] <= 1
    assert kpis["period_raised"] == sum(point["raised"] for point in months)
    assert kpis["period_closed"] == sum(point["closed"] for point in months)


def test_operations_endpoint_demo_mode() -> None:
    response = client.get("/api/analytics/operations")
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "demo"
    assert len(body["months"]) == 12
    assert body["months"][0]["month"] < body["months"][-1]["month"]
    kpis = body["kpis"]
    assert kpis["backlog"] == kpis["open_alerts"] + kpis["investigating"]
    assert kpis["scored_queue_size"] >= 1
    assert isinstance(body["notes"], list)
    assert body["notes"]


def test_fill_month_gaps_preserves_counts() -> None:
    filled = RiskRepository._fill_month_gaps(
        [
            {
                "month": "2099-01",
                "raised": 10,
                "closed": 7,
                "transaction_value_usd": 100.0,
                "sla_breaches": 2,
                "false_positives": 5,
                "true_positives": 2,
                "median_review_hours": 12.0,
            }
        ],
        count=3,
    )
    assert len(filled) == 3
    assert all(item["raised"] >= 0 for item in filled)
