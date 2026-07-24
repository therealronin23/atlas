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


def test_connection_refused_failclosed_not_a_crash() -> None:
    """Bug real 2026-07-24 (mató la corrida completa de ~2100 candidatos en
    el primer fallo de red): solo se capturaba HTTPError (respuestas HTTP con
    código) -- un fallo de CONEXIÓN (rechazada, DNS, timeout) es URLError, no
    HTTPError, y no se capturaba -- el batch de horas crasheaba entero en el
    primer candidato inalcanzable, algo garantizado a escala de internet."""
    from atlas.mcp.http_mcp_transport import urllib_fetcher_with_headers

    # Puerto local casi con certeza cerrado -- conexión rechazada real, sin mock.
    status, text, headers = urllib_fetcher_with_headers(
        "GET", "http://127.0.0.1:1", None, {}
    )
    assert status == 0
    assert headers == {}


def test_dns_failure_failclosed_not_a_crash() -> None:
    from atlas.mcp.http_mcp_transport import urllib_fetcher_with_headers

    status, text, headers = urllib_fetcher_with_headers(
        "GET", "https://this-domain-genuinely-does-not-exist-atlas-test.invalid", None, {}
    )
    assert status == 0
