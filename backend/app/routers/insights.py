from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_insights_service, get_repository
from app.models.schemas import (
    ActionableInsight,
    InsightDecisionRequest,
    InsightDecisionResponse,
    InsightEmailDraftRequest,
)
from app.services.actionable_insights import ActionableInsightsService
from app.services.repository import RiskRepository


router = APIRouter(prefix="/alerts", tags=["actionable insights"])


@router.get("/{alert_id}/insights", response_model=ActionableInsight)
def get_insights(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    insights: ActionableInsightsService = Depends(get_insights_service),
) -> ActionableInsight:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    cached = insights.get_insight(alert_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="No actionable insight generated yet")
    return cached


@router.post("/{alert_id}/insights", response_model=ActionableInsight)
def generate_insights(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    insights: ActionableInsightsService = Depends(get_insights_service),
) -> ActionableInsight:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return insights.generate_insight(alert_id, refresh=True)


@router.post("/{alert_id}/insights/decision", response_model=InsightDecisionResponse)
def decide_insights(
    alert_id: str,
    body: InsightDecisionRequest,
    repository: RiskRepository = Depends(get_repository),
    insights: ActionableInsightsService = Depends(get_insights_service),
) -> InsightDecisionResponse:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    try:
        insight, record = insights.apply_decision(alert_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="No actionable insight generated yet") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return InsightDecisionResponse(insight=insight, decision=record)


@router.post("/{alert_id}/insights/email", response_model=ActionableInsight)
def draft_csuite_email(
    alert_id: str,
    body: InsightEmailDraftRequest = InsightEmailDraftRequest(),
    repository: RiskRepository = Depends(get_repository),
    insights: ActionableInsightsService = Depends(get_insights_service),
) -> ActionableInsight:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    try:
        email = insights.build_csuite_email(alert_id, decision=body.decision)
        return insights.update_draft_email(alert_id, email)
    except KeyError:
        raise HTTPException(status_code=404, detail="No actionable insight generated yet") from None
