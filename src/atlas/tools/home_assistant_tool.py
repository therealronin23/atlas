"""
Atlas Core — Home Assistant Tool (absorbido de Hermes-Agent, 2026-07-18).

Capacidad genuinamente nueva (Atlas no tenía casa inteligente, ver
docs/design/absorption_master_plan.md — "Aligns directly with the founding
principle... cualquier hardware, se adapta"). REST API de Home Assistant
(LAN local por diseño — HASS_URL no pasa por SSRFBridge, a diferencia de
CrawlerTool: aquí el destino local ES el propósito, no un intento de pivote).

La lista de dominios de servicio bloqueados y la validación de entity_id/
service se absorben FIELES al original — es lógica de seguridad real,
motivada (Home Assistant no tiene control de acceso a nivel de servicio;
domains como shell_command/hassio permiten ejecución de comandos o apagado
del host). Encima: credencial explícita (HASS_TOKEN), auditoría Merkle,
call_service clasificado mutate/HITL (list_entities/get_state son solo
lectura, corren inline).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger

DEFAULT_URL = "http://homeassistant.local:8123"

# Mismas regex que el original: entity_id tipo "light.living_room", service
# domain/name solo minúsculas+dígitos+guion_bajo — evita path traversal en
# /api/services/{domain}/{service}.
_ENTITY_ID_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
_SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Dominios de servicio bloqueados — ejecutan código/comandos en el host de HA
# o abren SSRF. HA no tiene control de acceso por servicio: la seguridad va
# aquí, en la capa de Atlas. NUNCA relajar esta lista sin motivo explícito.
BLOCKED_SERVICE_DOMAINS = frozenset({
    "shell_command", "command_line", "python_script",
    "pyscript", "hassio", "rest_command",
})


@dataclass(frozen=True)
class HomeAssistantResult:
    action: str
    success: bool
    data: dict[str, Any]
    error: str | None = None


class HomeAssistantTool:
    """Control de Home Assistant gobernado (lectura inline, escritura HITL)."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        token_env: str = "HASS_TOKEN",
        merkle: MerkleLogger | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._base_url = (base_url or DEFAULT_URL).rstrip("/")
        self._token_env = token_env
        self._merkle = merkle
        self._timeout_s = timeout_s

    def list_entities(
        self, domain: str | None = None, area: str | None = None,
    ) -> HomeAssistantResult:
        result = self._get("/api/states")
        if not result.success:
            return result
        states = result.data.get("_raw", [])
        if domain:
            states = [s for s in states if s.get("entity_id", "").startswith(f"{domain}.")]
        if area:
            area_lower = area.lower()
            states = [
                s for s in states
                if area_lower in (s.get("attributes", {}).get("friendly_name", "") or "").lower()
            ]
        entities = [
            {
                "entity_id": s["entity_id"], "state": s["state"],
                "friendly_name": s.get("attributes", {}).get("friendly_name", ""),
            }
            for s in states
        ]
        self._log("home_assistant.list_entities", "ok", risk_level="safe",
                   payload={"domain": domain, "area": area, "count": len(entities)})
        return HomeAssistantResult(
            action="list_entities", success=True, data={"count": len(entities), "entities": entities},
        )

    def get_state(self, entity_id: str) -> HomeAssistantResult:
        if not _ENTITY_ID_RE.match(entity_id):
            error = f"entity_id inválido: {entity_id!r}"
            self._log("home_assistant.get_state", "failed", risk_level="safe", payload={"error": error})
            return HomeAssistantResult(action="get_state", success=False, data={}, error=error)
        result = self._get(f"/api/states/{entity_id}")
        if not result.success:
            return result
        self._log("home_assistant.get_state", "ok", risk_level="safe", payload={"entity_id": entity_id})
        return HomeAssistantResult(action="get_state", success=True, data=result.data.get("_raw", {}))

    def call_service(
        self, domain: str, service: str,
        entity_id: str | None = None, data: dict[str, Any] | None = None,
    ) -> HomeAssistantResult:
        """MUTA estado real del mundo (enciende luces, mueve persianas, etc.).
        Clasificado mutate/HITL en el loop agéntico — ver agentic_helpers.py."""
        if not _SERVICE_NAME_RE.match(domain) or not _SERVICE_NAME_RE.match(service):
            error = f"domain/service inválido: {domain!r}.{service!r}"
            self._log("home_assistant.call_service", "blocked", risk_level="high",
                       payload={"error": error})
            return HomeAssistantResult(action="call_service", success=False, data={}, error=error)

        if domain in BLOCKED_SERVICE_DOMAINS:
            error = f"dominio de servicio bloqueado por seguridad: {domain!r}"
            self._log("home_assistant.call_service", "blocked", risk_level="critical",
                       payload={"domain": domain, "service": service, "error": error})
            return HomeAssistantResult(action="call_service", success=False, data={}, error=error)

        if entity_id is not None and not _ENTITY_ID_RE.match(entity_id):
            error = f"entity_id inválido: {entity_id!r}"
            self._log("home_assistant.call_service", "failed", risk_level="safe",
                       payload={"error": error})
            return HomeAssistantResult(action="call_service", success=False, data={}, error=error)

        payload: dict[str, Any] = dict(data or {})
        if entity_id:
            payload["entity_id"] = entity_id

        result = self._post(f"/api/services/{domain}/{service}", payload)
        if not result.success:
            return HomeAssistantResult(action="call_service", success=False, data={}, error=result.error)
        self._log(
            "home_assistant.call_service", "ok", risk_level="moderate",
            payload={"domain": domain, "service": service, "entity_id": entity_id},
        )
        return HomeAssistantResult(action="call_service", success=True, data=result.data.get("_raw", {}))

    def _token(self) -> str:
        return os.environ.get(self._token_env, "")

    def _get(self, path: str) -> HomeAssistantResult:
        token = self._token()
        if not token:
            error = f"{self._token_env} no está definida en el entorno"
            self._log("home_assistant.request", "failed", risk_level="moderate", payload={"error": error})
            return HomeAssistantResult(action="get", success=False, data={}, error=error)
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        return self._send(req)

    def _post(self, path: str, body: dict[str, Any]) -> HomeAssistantResult:
        token = self._token()
        if not token:
            error = f"{self._token_env} no está definida en el entorno"
            self._log("home_assistant.request", "failed", risk_level="moderate", payload={"error": error})
            return HomeAssistantResult(action="post", success=False, data={}, error=error)
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> HomeAssistantResult:
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                raw = json.loads(resp.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}"
            self._log("home_assistant.request", "failed", risk_level="moderate",
                       payload={"error": error, "duration_ms": int((time.perf_counter() - start) * 1000)})
            return HomeAssistantResult(action="request", success=False, data={}, error=error)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._log("home_assistant.request", "failed", risk_level="moderate",
                       payload={"error": error, "duration_ms": int((time.perf_counter() - start) * 1000)})
            return HomeAssistantResult(action="request", success=False, data={}, error=error)
        return HomeAssistantResult(action="request", success=True, data={"_raw": raw})

    def _log(
        self, action: str, result: str, *,
        risk_level: str = "safe", payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action, agent="home_assistant.tool", result=result,
            risk_level=risk_level, payload=payload or {},
        )
