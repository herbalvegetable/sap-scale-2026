from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _credential_defaults() -> dict[str, str]:
    path = ROOT_DIR / "team_08_credentials.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    database = payload.get("database", {})
    ai_core = payload.get("ai_core", {})
    return {
        "HANA_HOST": str(database.get("host", "")),
        "HANA_PORT": str(database.get("port", "443")),
        "HANA_USER": str(database.get("username", "")),
        "HANA_PASSWORD": str(database.get("password", "")),
        "HANA_SCHEMA": str(database.get("schema", "TEAM_08")),
        "AICORE_CLIENT_ID": str(ai_core.get("client_id", "")),
        "AICORE_CLIENT_SECRET": str(ai_core.get("client_secret", "")),
        "AICORE_AUTH_URL": str(ai_core.get("auth_url", "")),
        "AICORE_API_URL": str(ai_core.get("api_url", "")),
        "AICORE_RESOURCE_GROUP": str(ai_core.get("resource_group", "team-08")),
    }


class Settings(BaseModel):
    app_name: str = "RiskAssess API"
    app_env: str = "development"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    data_mode: str = "auto"

    hana_host: str = ""
    hana_port: int = 443
    hana_user: str = ""
    hana_password: str = ""
    hana_schema: str = "TEAM_08"
    reference_schema: str = "TRUSTSPHERE_REFERENCE"
    hana_validate_certificate: bool = True

    aicore_client_id: str = ""
    aicore_client_secret: str = ""
    aicore_auth_url: str = ""
    aicore_api_url: str = ""
    aicore_resource_group: str = "team-08"
    aicore_deployment_id: str = ""
    aicore_model_name: str = "gpt-4o"
    aicore_timeout_seconds: float = 30.0

    prompt_version: str = "riskassess-1.0"

    @property
    def hana_configured(self) -> bool:
        return all((self.hana_host, self.hana_user, self.hana_password))

    @property
    def ai_core_configured(self) -> bool:
        return all(
            (
                self.aicore_client_id,
                self.aicore_client_secret,
                self.aicore_auth_url,
                self.aicore_api_url,
            )
        )


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    _load_env_file(ROOT_DIR / "team_08.env")
    _load_env_file(ROOT_DIR / ".env")
    defaults = _credential_defaults()

    def value(key: str, fallback: str = "") -> str:
        return os.getenv(key, defaults.get(key, fallback))

    origins = [item.strip() for item in value("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
    return Settings(
        app_env=value("APP_ENV", "development"),
        debug=_as_bool(value("DEBUG", "false"), False),
        cors_origins=origins,
        data_mode=value("DATA_MODE", "auto").lower(),
        hana_host=value("HANA_HOST"),
        hana_port=int(value("HANA_PORT", "443")),
        hana_user=value("HANA_USER"),
        hana_password=value("HANA_PASSWORD"),
        hana_schema=value("HANA_SCHEMA", "TEAM_08"),
        reference_schema=value("REFERENCE_SCHEMA", "TRUSTSPHERE_REFERENCE"),
        hana_validate_certificate=_as_bool(value("HANA_VALIDATE_CERTIFICATE", "true"), True),
        aicore_client_id=value("AICORE_CLIENT_ID"),
        aicore_client_secret=value("AICORE_CLIENT_SECRET"),
        aicore_auth_url=value("AICORE_AUTH_URL"),
        aicore_api_url=value("AICORE_API_URL"),
        aicore_resource_group=value("AICORE_RESOURCE_GROUP", "team-08"),
        aicore_deployment_id=value("AICORE_DEPLOYMENT_ID"),
        aicore_model_name=value("AICORE_MODEL_NAME", "gpt-4o"),
        aicore_timeout_seconds=float(value("AICORE_TIMEOUT_SECONDS", "30")),
        prompt_version=value("PROMPT_VERSION", "riskassess-1.0"),
    )
