"""Tests para KnowledgeSource protocol, RawRecord y HttpApiSource (T3, ADR-049)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.knowledge.sources import HttpApiSource, KnowledgeSource, OsvDepSource, RawRecord
from atlas.security.ssrf_bridge import BridgeDecision, SSRFBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allowed_bridge(domain: str = "api.example.com") -> SSRFBridge:
    bridge = MagicMock(spec=SSRFBridge)
    bridge.check.return_value = BridgeDecision(
        allowed=True,
        url="",
        reason="test-allowed",
        domain=domain,
    )
    return bridge


def _blocked_bridge(reason: str = "not in allowlist") -> SSRFBridge:
    bridge = MagicMock(spec=SSRFBridge)
    bridge.check.return_value = BridgeDecision(
        allowed=False,
        url="",
        reason=reason,
        domain="evil.internal",
    )
    return bridge


def _mock_fetcher(status: int = 200, text: str = '{"ok": true}'):
    """Devuelve un mock callable con la firma de Fetcher."""
    return MagicMock(return_value=(status, text))


# ---------------------------------------------------------------------------
# RawRecord
# ---------------------------------------------------------------------------

def test_raw_record_frozen() -> None:
    r = RawRecord(payload="hello", url="http://x.com", status=200)
    with pytest.raises((AttributeError, TypeError)):
        r.status = 999  # type: ignore[misc]


def test_raw_record_fields() -> None:
    r = RawRecord(payload="body", url="http://x.com/api", status=201)
    assert r.payload == "body"
    assert r.url == "http://x.com/api"
    assert r.status == 201


# ---------------------------------------------------------------------------
# KnowledgeSource Protocol
# ---------------------------------------------------------------------------

def test_http_api_source_satisfies_protocol() -> None:
    src = HttpApiSource("src-1", "test/domain", bridge=_allowed_bridge())
    assert isinstance(src, KnowledgeSource)


# ---------------------------------------------------------------------------
# HttpApiSource — url permitida (fetcher invocado)
# ---------------------------------------------------------------------------

def test_allowed_url_invokes_fetcher() -> None:
    fetcher = _mock_fetcher(200, "response body")
    bridge = _allowed_bridge()
    src = HttpApiSource("src-1", "test/domain", bridge=bridge, fetcher=fetcher)

    record = src._request("GET", "https://api.example.com/data")

    fetcher.assert_called_once()
    assert record.status == 200
    assert record.payload == "response body"
    assert record.url == "https://api.example.com/data"


def test_allowed_post_with_json_body() -> None:
    fetcher = _mock_fetcher(201, '{"id": 42}')
    bridge = _allowed_bridge()
    src = HttpApiSource("src-1", "test/domain", bridge=bridge, fetcher=fetcher)

    record = src._request("POST", "https://api.example.com/items", json_body={"name": "x"})

    args = fetcher.call_args
    method, url, body, headers = args[0]
    assert method == "POST"
    assert body is not None
    assert b'"name"' in body
    assert headers.get("Content-Type") == "application/json"
    assert record.status == 201


# ---------------------------------------------------------------------------
# HttpApiSource — url denegada (fetcher NO invocado, fail-closed)
# ---------------------------------------------------------------------------

def test_blocked_url_does_not_invoke_fetcher() -> None:
    fetcher = _mock_fetcher()
    bridge = _blocked_bridge("not in allowlist")
    src = HttpApiSource("src-1", "test/domain", bridge=bridge, fetcher=fetcher)

    record = src._request("GET", "https://evil.internal/secret")

    fetcher.assert_not_called()
    assert record.status == -1
    assert record.payload.startswith("blocked:")


def test_blocked_url_payload_contains_reason() -> None:
    fetcher = _mock_fetcher()
    bridge = _blocked_bridge("IP privada bloqueada")
    src = HttpApiSource("src-1", "test/domain", bridge=bridge, fetcher=fetcher)

    record = src._request("GET", "https://192.168.1.1/admin")

    assert "IP privada bloqueada" in record.payload
    fetcher.assert_not_called()


# ---------------------------------------------------------------------------
# fetch() base
# ---------------------------------------------------------------------------

def test_fetch_base_uses_get() -> None:
    fetcher = _mock_fetcher(200, "ok")
    bridge = _allowed_bridge()
    src = HttpApiSource("src-1", "test/domain", bridge=bridge, fetcher=fetcher)

    records = src.fetch("https://api.example.com/q")

    assert len(records) == 1
    assert records[0].status == 200
    args = fetcher.call_args[0]
    assert args[0] == "GET"


# ---------------------------------------------------------------------------
# OsvDepSource (T4, ADR-049)
# ---------------------------------------------------------------------------

def test_osv_dep_source_metadata() -> None:
    src = OsvDepSource()
    assert src.source_id == "osv.dev/pypi"
    assert src.domain == "security/cve"
    assert isinstance(src, KnowledgeSource)


def test_osv_dep_source_fetch_posts_to_osv(monkeypatch: pytest.MonkeyPatch) -> None:
    osv_payload = '{"vulns": [{"id": "GHSA-xxxx-yyyy-zzzz"}]}'
    fetcher = _mock_fetcher(200, osv_payload)
    bridge = _allowed_bridge("api.osv.dev")
    src = OsvDepSource(bridge=bridge, fetcher=fetcher)

    records = src.fetch("requests")

    assert len(records) == 1
    record = records[0]
    assert record.status == 200
    assert "vulns" in record.payload

    # Verifica que el fetcher recibió POST a la URL correcta con el body esperado
    method, url, body, headers = fetcher.call_args[0]
    assert method == "POST"
    assert url == "https://api.osv.dev/v1/query"
    assert body is not None
    assert b'"requests"' in body
    assert b'"PyPI"' in body


def test_osv_dep_source_ssrf_allowed_by_default() -> None:
    bridge = SSRFBridge()
    decision = bridge.check("https://api.osv.dev/v1/query")
    assert decision.allowed is True
