from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import (
    get_case_chat_service,
    get_insights_service,
    get_performance_chat_service,
    get_repository,
    get_scoring_engine,
    get_vector_store,
)
from app.main import app
from app.services.actionable_insights import ActionableInsightsService
from app.services.ai_core_client import AICoreClient
from app.services.case_chat import CaseChatService
from app.services.hana_client import HanaClient
from app.services.performance_chat import PerformanceChatService
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore


settings = Settings(data_mode="demo")
repository = RiskRepository(settings, HanaClient(settings))
scoring = ScoringEngine(settings, repository, AICoreClient(settings))
insights = ActionableInsightsService(settings, repository, scoring, AICoreClient(settings))
vector = HanaVectorStore(settings, HanaClient(settings))
chat = CaseChatService(settings, repository, scoring, AICoreClient(settings), vector)
perf_chat = PerformanceChatService(settings, repository, scoring, AICoreClient(settings))
app.dependency_overrides[get_repository] = lambda: repository
app.dependency_overrides[get_scoring_engine] = lambda: scoring
app.dependency_overrides[get_insights_service] = lambda: insights
app.dependency_overrides[get_vector_store] = lambda: vector
app.dependency_overrides[get_case_chat_service] = lambda: chat
app.dependency_overrides[get_performance_chat_service] = lambda: perf_chat
client = TestClient(app)


def test_alert_list_filters_and_paginates() -> None:
    response = client.get("/api/alerts", params={"page_size": 2, "tier": "high"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 2
    assert all(item["score"]["tier"] == "high" for item in payload["items"])


def test_alert_detail_and_score() -> None:
    alert_id = repository.all_alert_contexts()[0]["id"]
    detail = client.get(f"/api/alerts/{alert_id}")
    score = client.get(f"/api/alerts/{alert_id}/score")
    assert detail.status_code == 200
    assert score.status_code == 200
    score_body = score.json()
    assert len(score_body["factors"]) == 5
    assert score_body["confidence"]["level"] in {"high", "medium", "low"}
    assert score_body["confidence"]["reasons"]
    assert all("confidence" in factor for factor in score_body["factors"])


def test_unknown_alert_is_404() -> None:
    response = client.get("/api/alerts/does-not-exist")
    assert response.status_code == 404


def test_insights_generate_get_and_decision() -> None:
    alert_id = "ALT-2026-00841"
    missing = client.get(f"/api/alerts/{alert_id}/insights")
    assert missing.status_code == 404

    generated = client.post(f"/api/alerts/{alert_id}/insights")
    assert generated.status_code == 200
    body = generated.json()
    # Low key-driver confidence abstains from draft_sar → request_kyc
    assert body["recommended_action"] == "request_kyc"
    assert body["confidence"] == "low"
    assert body["status"] == "generated"
    assert "urgency_score" in body
    assert body["reasoning_trace"]
    assert any(item["rule_id"] == "CONF-ABSTAIN-01" for item in body["reasoning_trace"])

    cached = client.get(f"/api/alerts/{alert_id}/insights")
    assert cached.status_code == 200
    assert cached.json()["insight_id"] == body["insight_id"]

    decision = client.post(
        f"/api/alerts/{alert_id}/insights/decision",
        json={
            "decision": "approved",
            "reason_code": "agrees_with_rules",
            "free_text": "Evidence supports Draft SAR recommendation.",
        },
    )
    assert decision.status_code == 200
    payload = decision.json()
    assert payload["insight"]["status"] == "approved"
    assert payload["decision"]["framing"] == "decision_quality_audit"

    conflict = client.post(
        f"/api/alerts/{alert_id}/insights/decision",
        json={"decision": "overridden", "free_text": "retry"},
    )
    assert conflict.status_code == 409


def test_chat_thread_and_chart_post() -> None:
    alert_id = "ALT-2026-00828"
    thread = client.get(f"/api/alerts/{alert_id}/chat")
    assert thread.status_code == 200
    body = thread.json()
    assert len(body["suggestions"]) == 3
    chart_prompt = next(item["prompt"] for item in body["suggestions"] if item["id"] == "chart_activity")
    posted = client.post(f"/api/alerts/{alert_id}/chat", json={"message": chart_prompt})
    assert posted.status_code == 200
    reply = posted.json()
    assert reply["chart"]["chart_type"] == "activity_vs_baseline"
    assert reply["chart"]["points"]


def test_performance_chat_thread_and_chart_post() -> None:
    operations = client.get("/api/analytics/operations")
    assert operations.status_code == 200
    ops = operations.json()

    thread = client.get("/api/analytics/operations/chat", params={"range_months": 12})
    assert thread.status_code == 200
    body = thread.json()
    assert body["range_months"] == 12
    assert len(body["suggestions"]) == 3

    chart_prompt = next(item["prompt"] for item in body["suggestions"] if item["id"] == "chart_raised_closed")
    posted = client.post(
        "/api/analytics/operations/chat",
        json={"message": chart_prompt, "range_months": 12},
    )
    assert posted.status_code == 200
    reply = posted.json()
    assert reply["chart"]["chart_type"] == "raised_vs_closed"
    assert len(reply["chart"]["points"]) == 12
    assert reply["chart"]["points"][0]["raised"] == ops["months"][0]["raised"]
    assert reply["chart"]["points"][-1]["closed"] == ops["months"][-1]["closed"]

    scoped = client.post(
        "/api/analytics/operations/chat",
        json={"message": "What is the current backlog?", "range_months": 6},
    )
    assert scoped.status_code == 200
    scoped_body = scoped.json()
    assert scoped_body["range_months"] == 6
    assert scoped_body["reply"]
    assert any(c["kind"] in {"kpi", "definition", "chart", "note", "metric"} for c in scoped_body["citations"])
