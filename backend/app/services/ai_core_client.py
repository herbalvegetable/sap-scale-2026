from __future__ import annotations

import json
import logging
import time
from threading import Lock
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class AICoreError(RuntimeError):
    pass


class AICoreClient:
    """Minimal SAP AI Core client for OpenAI-compatible deployments."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._deployment_id: str | None = settings.aicore_deployment_id or None
        self._deployment_url: str | None = None
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        return self.settings.ai_core_configured

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self.configured:
            raise AICoreError("SAP AI Core credentials are not configured")
        with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            url = f"{self.settings.aicore_auth_url.rstrip('/')}/oauth/token"
            try:
                response = httpx.post(
                    url,
                    data={"grant_type": "client_credentials"},
                    auth=(self.settings.aicore_client_id, self.settings.aicore_client_secret),
                    timeout=self.settings.aicore_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise AICoreError(f"SAP AI Core authentication failed: {exc}") from exc
            self._token = payload["access_token"]
            self._token_expires_at = time.time() + int(payload.get("expires_in", 600))
            return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "AI-Resource-Group": self.settings.aicore_resource_group,
            "Content-Type": "application/json",
        }

    def ping(self) -> bool:
        try:
            self._get_token()
            return True
        except AICoreError as exc:
            logger.warning("SAP AI Core is unavailable: %s", exc)
            return False

    def list_deployments(self) -> list[dict[str, Any]]:
        url = f"{self.settings.aicore_api_url.rstrip('/')}/v2/lm/deployments"
        try:
            response = httpx.get(url, headers=self._headers(), timeout=self.settings.aicore_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AICoreError(f"Could not list SAP AI Core deployments: {exc}") from exc
        return list(payload.get("resources", payload.get("deployments", [])))

    def _resolve_deployment_url(self) -> str:
        if self._deployment_url:
            return self._deployment_url
        if self._deployment_id:
            self._deployment_url = (
                f"{self.settings.aicore_api_url.rstrip('/')}"
                f"/v2/inference/deployments/{self._deployment_id}"
            )
            return self._deployment_url
        deployments = self.list_deployments()
        for deployment in sorted(
            deployments,
            key=lambda item: str(item.get("createdAt", "")),
            reverse=True,
        ):
            status = str(deployment.get("status", "")).upper()
            scenario = str(deployment.get("scenarioId", "")).lower()
            if scenario == "orchestration" and status in {"RUNNING", "READY", "COMPLETED"}:
                self._deployment_id = str(deployment.get("id") or deployment.get("deploymentId"))
                self._deployment_url = str(
                    deployment.get("deploymentUrl")
                    or f"{self.settings.aicore_api_url.rstrip('/')}/v2/inference/deployments/{self._deployment_id}"
                )
                return self._deployment_url
        raise AICoreError("No running SAP AI Core orchestration deployment found")

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        candidates = [payload, payload.get("orchestration_result", {}), payload.get("result", {})]
        for candidate in candidates:
            try:
                return str(candidate["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError):
                continue
        raise AICoreError("SAP AI Core returned an unexpected response shape")

    def chat_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._resolve_deployment_url().rstrip('/')}/completion"
        request = {
            "orchestration_config": {
                "module_configurations": {
                    "templating_module_config": {
                        "template": [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": json.dumps(user_payload, default=str),
                            },
                        ]
                    },
                    "llm_module_config": {
                        "model_name": self.settings.aicore_model_name,
                        "model_version": "latest",
                        "model_params": {
                            "temperature": 0,
                            "max_tokens": 1800,
                            "response_format": {"type": "json_object"},
                        },
                    },
                }
            }
        }
        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                json=request,
                timeout=self.settings.aicore_timeout_seconds,
            )
            response.raise_for_status()
            content = self._extract_content(response.json())
            return json.loads(content)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise AICoreError(f"SAP AI Core inference failed: {exc}") from exc
