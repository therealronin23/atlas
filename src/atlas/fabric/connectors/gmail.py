"""GmailReadOnlyConnector — primer conector REAL de Atlas (ADR-065).

Read-only. Cliente propio: SOLO stdlib (urllib), sin depender del MCP
conducido por Claude ni de ninguna librería HTTP/cliente de terceros
añadida al proyecto — cero dependencia nueva (ver ADR-065 para el porqué).
El token OAuth se lee como referencia opaca de entorno (patrón `env:<VAR>`
de `atlas.fabric.auth_broker`) — Atlas nunca lo persiste, devuelve ni loguea.

`email.send` NO se implementa aquí: sigue hard-gated en el PolicyEngine
(`pol_hard_personal_channel_send` + capability `email.send` de risk HIGH en
`atlas.fabric.capabilities`) exista o no este conector.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
_TIMEOUT_SECONDS = 10


class GmailReadOnlyConnector:
    """Cliente Gmail read-only con cliente propio (urllib de stdlib)."""

    #: Documenta la invariante: este conector SOLO lee y devuelve datos con
    #: provenance; nunca escribe en memoria por su cuenta. La decisión de
    #: ingerir vive en otra capa (fuera de este módulo), nunca aquí.
    WRITES_TO_MEMORY = False

    def __init__(self, token_env_var: str = "GMAIL_OAUTH_TOKEN") -> None:
        self._token_env_var = token_env_var

    def available(self) -> bool:
        """True si hay un token en `env:<token_env_var>`. NUNCA devuelve ni
        loguea el valor — solo comprueba presencia, como
        `AuthBroker.reference_available`."""
        return bool(os.environ.get(self._token_env_var))

    def list_messages(self, query: str = "", max_results: int = 10) -> dict[str, Any]:
        """Lista mensajes vía la API real de Gmail. Sin red si falta token."""
        if not self.available():
            return {
                "ok": False,
                "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "detail": (
                    f"falta el token OAuth en env:{self._token_env_var}; "
                    "el operador debe aportarlo"
                ),
                "real": False,
            }

        params: dict[str, str] = {"maxResults": str(max_results)}
        if query:
            params["q"] = query
        url = f"{_GMAIL_MESSAGES_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {os.environ[self._token_env_var]}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Solo código/motivo, jamás el request/headers (llevarían el
            # token): así el detalle nunca puede filtrarlo.
            return {
                "ok": False,
                "status": "error",
                "detail": f"gmail api error HTTP {exc.code}",
                "real": True,
            }
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "status": "error",
                "detail": f"gmail api error de red: {exc.reason}",
                "real": True,
            }

        messages = body.get("messages", [])
        return {
            "ok": True,
            "real": True,
            "provenance": "gmail_api_readonly",
            "messages": messages,
            "count": len(messages),
        }

    def capabilities(self) -> list[str]:
        """email.send NUNCA aparece aquí: hard-gated en el PolicyEngine
        con o sin este conector (ver policy.py + capabilities.py)."""
        return ["email.read", "email.draft"]
