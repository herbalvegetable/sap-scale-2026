from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_performance_chat_service, get_repository, get_scoring_engine
from app.models.schemas import (
    OperationsDashboard,
    PerformanceChatRequest,
    PerformanceChatResponse,
    PerformanceChatThreadResponse,
    RangeMonths,
)
from app.services.performance_chat import PerformanceChatService
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine


router = APIRouter(prefix="/analytics", tags=["analytics"])


def _high_priority_ids(repository: RiskRepository, scoring: ScoringEngine) -> set[str]:
    contexts = repository.all_alert_contexts()
    return {
        str(row["id"])
        for row in contexts
        if scoring.score_alert(str(row["id"]), use_ai=False).tier == "high"
        and str(row.get("status")).lower() in {"open", "investigating"}
    }


def _parse_range_months(value: int) -> RangeMonths:
    if value not in (6, 12):
        raise HTTPException(status_code=422, detail="range_months must be 6 or 12")
    return cast(RangeMonths, value)


@router.get("/operations", response_model=OperationsDashboard)
def operations_dashboard(
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> OperationsDashboard:
    payload = repository.get_operations_dashboard(
        high_priority_ids=_high_priority_ids(repository, scoring)
    )
    return OperationsDashboard.model_validate(payload)


@router.get("/operations/chat", response_model=PerformanceChatThreadResponse)
def get_operations_chat_thread(
    range_months: int = Query(default=12, description="History window: 6 or 12"),
    chat: PerformanceChatService = Depends(get_performance_chat_service),
) -> PerformanceChatThreadResponse:
    return chat.get_thread(_parse_range_months(range_months))


@router.post("/operations/chat", response_model=PerformanceChatResponse)
def post_operations_chat_message(
    request: PerformanceChatRequest,
    chat: PerformanceChatService = Depends(get_performance_chat_service),
) -> PerformanceChatResponse:
    return chat.chat(request)
