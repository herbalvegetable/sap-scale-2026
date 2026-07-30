from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_repository, get_scoring_engine
from app.main import app
from app.services.ai_core_client import AICoreClient
from app.services.hana_client import HanaClient
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine


settings = Settings(data_mode="demo")
repository = RiskRepository(settings, HanaClient(settings))
scoring = ScoringEngine(settings, repository, AICoreClient(settings))
app.dependency_overrides[get_repository] = lambda: repository
app.dependency_overrides[get_scoring_engine] = lambda: scoring
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
    assert len(score.json()["factors"]) == 5


def test_unknown_alert_is_404() -> None:
    response = client.get("/api/alerts/does-not-exist")
    assert response.status_code == 404
