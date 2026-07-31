from functools import lru_cache

from app.config import get_settings
from app.services.actionable_insights import ActionableInsightsService
from app.services.ai_core_client import AICoreClient
from app.services.case_chat import CaseChatService
from app.services.hana_client import HanaClient
from app.services.performance_chat import PerformanceChatService
from app.services.rag_pipeline import RiskIntelligenceService
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine
from app.services.vector_store import HanaVectorStore


@lru_cache
def get_hana() -> HanaClient:
    return HanaClient(get_settings())


@lru_cache
def get_ai_core() -> AICoreClient:
    return AICoreClient(get_settings())


@lru_cache
def get_repository() -> RiskRepository:
    return RiskRepository(get_settings(), get_hana())


@lru_cache
def get_scoring_engine() -> ScoringEngine:
    return ScoringEngine(get_settings(), get_repository(), get_ai_core())


@lru_cache
def get_vector_store() -> HanaVectorStore:
    return HanaVectorStore(get_settings(), get_hana())


@lru_cache
def get_intelligence_service() -> RiskIntelligenceService:
    return RiskIntelligenceService(
        get_settings(),
        get_repository(),
        get_scoring_engine(),
        get_ai_core(),
        get_vector_store(),
    )


@lru_cache
def get_insights_service() -> ActionableInsightsService:
    return ActionableInsightsService(
        get_settings(),
        get_repository(),
        get_scoring_engine(),
        get_ai_core(),
    )


@lru_cache
def get_case_chat_service() -> CaseChatService:
    return CaseChatService(
        get_settings(),
        get_repository(),
        get_scoring_engine(),
        get_ai_core(),
        get_vector_store(),
    )


@lru_cache
def get_performance_chat_service() -> PerformanceChatService:
    return PerformanceChatService(
        get_settings(),
        get_repository(),
        get_scoring_engine(),
        get_ai_core(),
    )
