"""TDD — urllib_fetcher_with_headers: variante real (no mockeada en producción)
del fetcher que SÍ expone los headers de respuesta, para que HttpMcpTransport
pueda capturar Mcp-Session-Id (ver http_mcp_transport.py)."""

from __future__ import annotations


def test_returns_3tuple_with_headers_dict() -> None:
    from atlas.mcp.http_mcp_transport import urllib_fetcher_with_headers

    result = urllib_fetcher_with_headers("GET", "https://example.com", None, {})
    assert len(result) == 3
    status, text, headers = result
    assert isinstance(status, int)
    assert isinstance(headers, dict)
