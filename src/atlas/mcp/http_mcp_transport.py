"""Etapa 2B de ADR-075 — probe de protocolo MCP sobre HTTP remoto.

Implementa ``McpTransport`` (mismo Protocol que ``StdioTransport``,
``transport.py``) para el 88.5% del catálogo (``transport: http``) que no
tiene código fuente descargable (servidor alojado por terceros, autocrítica
ADR-075). Solo negocia protocolo (``initialize``/``tools/list``) -- **nunca
expone un helper para invocar una tool real** (``tools/call``), eso es
explícitamente fuera de alcance de un probe de admisión (I3: el LLM vivo
nunca toca esto; una tool real solo se invoca tras admisión HITL, ADR-075 I5).

Egress SIEMPRE vía una instancia EFÍMERA de ``SSRFBridge`` con
``extra_allowed={dominio_de_este_endpoint}`` -- pasada por el caller, nunca
la instancia compartida de producción. Esto es lo que hace seguro sondear
1869 dominios de terceros sin envenenar permanentemente el control de egress
de Atlas (ver discusión ADR-075, hallazgo 2026-07-24).
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from atlas.mcp.transport import McpProtocolError
from atlas.security.ssrf_bridge import SSRFBridge

Fetcher = Any  # firma: (method, url, data: bytes, headers: dict) -> (status, text)


def _strip_sse_framing(text: str) -> str:
    """MCP Streamable HTTP permite responder como SSE (``event:``/``data:``
    líneas) en vez de JSON plano -- verificado en vivo contra un endpoint
    remoto real (api.inference.sh) que SÍ usa este framing. Toma el ÚLTIMO
    ``data:`` (el mensaje JSON-RPC de respuesta; líneas ``event:`` se ignoran).
    Si no hay framing SSE, devuelve el texto tal cual (JSON plano, camino ya
    cubierto)."""
    if "data:" not in text:
        return text
    data_lines = [ln[len("data:"):].strip() for ln in text.splitlines() if ln.startswith("data:")]
    return data_lines[-1] if data_lines else text


class HttpMcpTransport:
    """JSON-RPC 2.0 sobre HTTP POST (MCP Streamable HTTP), mismo envelope que
    ``StdioTransport`` (``jsonrpc``/``id``/``method``/``params``)."""

    def __init__(
        self,
        url: str,
        *,
        fetcher: Fetcher,
        allowed_domains: set[str] | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._url = url
        self._fetcher = fetcher
        self._timeout = float(timeout_seconds)
        domain = urlparse(url).hostname or ""
        # Efímera, propia de este transporte -- nunca la compartida.
        self._bridge = SSRFBridge(extra_allowed=allowed_domains if allowed_domains is not None else {domain})
        self._next_id = 1

    def _post(self, payload: dict[str, Any]) -> tuple[int, str]:
        decision = self._bridge.check(self._url)
        if not decision.allowed:
            raise McpProtocolError(f"egress bloqueado por allowlist: {decision.reason}")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            # MCP Streamable HTTP exige este Accept -- sin él, servidores
            # reales responden 400/406 (verificado en vivo, 2026-07-24,
            # contra api.inference.sh). Antes de este fix, muchos "HTTP 406"
            # del batch real eran justo esto: falta de conformidad propia.
            "Accept": "application/json, text/event-stream",
            "User-Agent": "atlas-core-vetting-probe",
        }
        status, text = self._fetcher("POST", self._url, data, headers)
        return status, text

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        status, text = self._post(payload)
        if status not in (200, 202):
            raise McpProtocolError(f"HTTP {status} del endpoint remoto")
        if not text.strip():
            raise McpProtocolError("respuesta vacía del endpoint remoto")
        body = _strip_sse_framing(text)
        try:
            msg = json.loads(body)
        except json.JSONDecodeError as exc:
            raise McpProtocolError(f"respuesta no-JSON: {text[:200]}") from exc
        if not isinstance(msg, dict):
            raise McpProtocolError("respuesta JSON-RPC no es un objeto")
        if "error" in msg:
            err = msg["error"] or {}
            raise McpProtocolError(f"server error {err.get('code')}: {err.get('message', '')}")
        return msg.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        # Notificaciones no esperan cuerpo útil (202 típico) -- fire-and-forget,
        # pero SIGUE pasando por el mismo gate de egress fail-closed.
        self._post(payload)

    def close(self) -> None:
        """No-op: sin proceso/conexión persistente que liberar (POST simple,
        sin sesión Mcp-Session-Id -- ver limitación en el docstring del módulo
        si un server exige sesión, el probe falla honesto, no se finge éxito)."""
