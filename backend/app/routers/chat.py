from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_case_chat_service, get_repository
from app.models.schemas import ChatRequest, ChatResponse, ChatThreadResponse
from app.services.case_chat import CaseChatService
from app.services.repository import RiskRepository


router = APIRouter(prefix="/alerts", tags=["case assistant"])


@router.get("/{alert_id}/chat", response_model=ChatThreadResponse)
def get_chat_thread(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    chat: CaseChatService = Depends(get_case_chat_service),
) -> ChatThreadResponse:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return chat.get_thread(alert_id)


@router.post("/{alert_id}/chat", response_model=ChatResponse)
def post_chat_message(
    alert_id: str,
    body: ChatRequest,
    repository: RiskRepository = Depends(get_repository),
    chat: CaseChatService = Depends(get_case_chat_service),
) -> ChatResponse:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return chat.chat(alert_id, body)
