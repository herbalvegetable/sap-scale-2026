from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_intelligence_service, get_repository
from app.models.schemas import Explanation
from app.services.rag_pipeline import RiskIntelligenceService
from app.services.repository import RiskRepository


router = APIRouter(prefix="/alerts", tags=["risk intelligence"])


@router.get("/{alert_id}/explanation", response_model=Explanation)
def get_explanation(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    intelligence: RiskIntelligenceService = Depends(get_intelligence_service),
) -> Explanation:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return intelligence.explain_alert(alert_id)


@router.post("/{alert_id}/explain", response_model=Explanation)
def refresh_explanation(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    intelligence: RiskIntelligenceService = Depends(get_intelligence_service),
) -> Explanation:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return intelligence.explain_alert(alert_id, refresh=True)
