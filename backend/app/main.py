from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.dependencies import get_ai_core, get_hana, get_repository
from app.models.schemas import ServiceHealth
from app.routers import alerts, chat, entities, insights, intelligence


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Financial-crime alert triage and risk intelligence.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(alerts.router)
api.include_router(intelligence.router)
api.include_router(insights.router)
api.include_router(chat.router)
api.include_router(entities.router)


@api.get("/health", response_model=ServiceHealth, tags=["operations"])
def health() -> ServiceHealth:
    hana = get_hana()
    ai_core = get_ai_core()
    repository = get_repository()
    hana_state = "not_configured" if not hana.configured else ("connected" if hana.ping() else "unavailable")
    ai_state = "not_configured" if not ai_core.configured else ("connected" if ai_core.ping() else "unavailable")
    degraded = repository.mode == "demo" or ai_state != "connected"
    return ServiceHealth(
        status="degraded" if degraded else "healthy",
        data_mode=repository.mode,
        hana=hana_state,
        ai_core=ai_state,
        model=settings.aicore_model_name,
    )


app.include_router(api)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}
