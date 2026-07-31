from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_repository
from app.models.schemas import AuditPage
from app.services.privacy import privacy_meta
from app.services.repository import RiskRepository

router = APIRouter(tags=["operations"])


@router.get("/audit", response_model=AuditPage)
def list_audit(
    limit: int = Query(50, ge=1, le=200),
    alert_id: str | None = Query(None),
    repository: RiskRepository = Depends(get_repository),
) -> AuditPage:
    items = repository.list_audit_events(alert_id=alert_id, limit=limit)
    return AuditPage(items=items, total=len(items), privacy=privacy_meta())
