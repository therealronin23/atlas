"""
TDD — HttpMcpTransport: etapa 2B de ADR-075.

Implementa el mismo Protocol ``McpTransport`` que ``StdioTransport``
(request/notify/close), pero JSON-RPC 2.0 sobre HTTP POST (MCP Streamable
HTTP) contra un endpoint remoto de terceros -- nunca invoca una tool real
(``tools/call``), solo negocia protocolo (``initialize``/``tools/list``).

Egress SIEMPRE gated por una instancia EFÍMERA de SSRFBridge con
``extra_allowed={ese_dominio}`` -- nunca la instancia compartida de
producción (violaría "allowlist curada uno a uno").
"""

from __future__ import annotations

import json
import socket
from unittest.mock import patch

# Mismo patrón que tests/test_ssrf_bridge.py: SSRFBridge.check() hace
# resolución DNS real -- se mockea socket.getaddrinfo, no se depende de un
# dominio de verdad resoluble.
_FAKE_ADDR = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


def _fetcher_returning(status: int, body: str):
    def f(method, url, data, headers):
        return status, body
    return f


def test_request_sends_jsonrpc_envelope_and_parses_result() -> None:
    from atlas.mcp.http_mcp_transport import HttpMcpTransport

    seen = {}

    def fetcher(method, url, data, headers):
        seen["method"] = method
        seen["url"] = url
        seen["body"] = json.loads(data.decode())
        return 200, json.dumps({"jsonrpc": "2.0", "id": seen["body"]["id"], "result": {"tools": []}})

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=fetcher)
    with patch("socket.getaddrinfo", return_value=_FAKE_ADDR):
        result = t.request("tools/list", {})
    assert result == {"tools": []}
    assert seen["method"] == "POST"
    assert seen["body"]["jsonrpc"] == "2.0"
    assert seen["body"]["method"] == "tools/list"


def test_request_parses_sse_framed_response() -> None:
    """Hallazgo real (2026-07-24, probado contra api.inference.sh en vivo):
    MCP Streamable HTTP puede responder como SSE (``data: {...}``) en vez de
    JSON plano -- el propio spec lo permite. Sin despojar el framing, una
    respuesta REAL y válida se descartaba como "no-JSON"."""
    from atlas.mcp.http_mcp_transport import HttpMcpTransport

    def fetcher(method, url, data, headers):
        body = json.loads(data.decode())
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "x"}]}})
        return 200, f"event: message\ndata: {payload}\n\n"

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=fetcher)
    with patch("socket.getaddrinfo", return_value=_FAKE_ADDR):
        result = t.request("tools/list", {})
    assert result == {"tools": [{"name": "x"}]}


def test_request_raises_on_jsonrpc_error() -> None:
    from atlas.mcp.http_mcp_transport import HttpMcpTransport
    from atlas.mcp.transport import McpProtocolError

    def fetcher(method, url, data, headers):
        body = json.loads(data.decode())
        return 200, json.dumps({"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "no existe"}})

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=fetcher)
    with patch("socket.getaddrinfo", return_value=_FAKE_ADDR):
        try:
            t.request("initialize", {})
            assert False, "esperaba McpProtocolError"
        except McpProtocolError as exc:
            assert "no existe" in str(exc)


def test_request_fails_closed_on_egress_blocked() -> None:
    """El dominio del endpoint NO está en la allowlist efímera pasada al
    transporte -- SSRFBridge lo bloquea ANTES de invocar el fetcher (mismo
    contrato que HttpApiSource: el fetcher ni se llama)."""
    from atlas.mcp.http_mcp_transport import HttpMcpTransport
    from atlas.mcp.transport import McpProtocolError

    called = []

    def fetcher(method, url, data, headers):
        called.append(url)
        return 200, "{}"

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=fetcher, allowed_domains=set())
    try:
        t.request("tools/list", {})
        assert False, "esperaba McpProtocolError (egress bloqueado)"
    except McpProtocolError as exc:
        assert "allowlist" in str(exc).lower() or "bloque" in str(exc).lower()
    assert called == []  # el fetcher NUNCA se invocó


def test_notify_does_not_raise_on_202_no_body() -> None:
    from atlas.mcp.http_mcp_transport import HttpMcpTransport

    def fetcher(method, url, data, headers):
        return 202, ""

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=fetcher)
    with patch("socket.getaddrinfo", return_value=_FAKE_ADDR):
        t.notify("notifications/initialized", {})  # no debe lanzar


def test_transport_never_calls_tools_call_helper_absent() -> None:
    """Invariante I3/etapa-3 de ADR-075: este transporte no expone NINGÚN
    helper de conveniencia para invocar una tool real -- solo request/notify
    genéricos que el probe de protocolo usa exclusivamente para
    initialize/tools/list."""
    from atlas.mcp.http_mcp_transport import HttpMcpTransport

    assert not hasattr(HttpMcpTransport, "call_tool")
    assert not hasattr(HttpMcpTransport, "invoke_tool")


def test_close_is_noop_safe() -> None:
    from atlas.mcp.http_mcp_transport import HttpMcpTransport

    t = HttpMcpTransport("https://real.example.com/mcp", fetcher=_fetcher_returning(200, "{}"))
    t.close()  # no debe lanzar, no hay proceso/conexión persistente que liberar
