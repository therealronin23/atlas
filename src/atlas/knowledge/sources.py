"""
Atlas Core — KnowledgeSource protocol + RawRecord + HttpApiSource (T3, ADR-049).

Toda petición HTTP pasa primero por SSRFBridge.check(url). Si no está
permitida el fetcher NO se invoca (fail-closed): se devuelve un RawRecord
con status=-1 y payload="blocked:<reason>".
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from atlas.security.ssrf_bridge import SSRFBridge


# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawRecord:
    payload: str   # cuerpo de la respuesta tal cual (texto)
    url: str
    status: int


# Firma del fetcher inyectable: (method, url, body_bytes|None, headers) -> (status, text)
Fetcher = Callable[[str, str, bytes | None, dict[str, str]], tuple[int, str]]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class KnowledgeSource(Protocol):
    source_id: str
    domain: str

    def fetch(self, query: Any) -> list[RawRecord]: ...


# ---------------------------------------------------------------------------
# Fetcher por defecto (stdlib urllib, sin deps externas)
# ---------------------------------------------------------------------------

def _urllib_fetcher(
    method: str,
    url: str,
    body: bytes | None,
    headers: dict[str, str],
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HttpApiSource
# ---------------------------------------------------------------------------

class HttpApiSource:
    """
    Fuente HTTP genérica. Subclases concretas (p.ej. OsvDepSource) implementan
    `fetch`; la infraestructura de gate + fetcher vive aquí en `_request`.
    """

    def __init__(
        self,
        source_id: str,
        domain: str,
        *,
        bridge: SSRFBridge | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.source_id = source_id
        self.domain = domain
        self._bridge = bridge if bridge is not None else SSRFBridge()
        self._fetcher: Fetcher = fetcher if fetcher is not None else _urllib_fetcher

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> RawRecord:
        # Gate fail-closed: el fetcher NO se invoca si el bridge deniega.
        decision = self._bridge.check(url)
        if not decision.allowed:
            return RawRecord(
                payload=f"blocked:{decision.reason}",
                url=url,
                status=-1,
            )

        headers: dict[str, str] = {}
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"

        status, text = self._fetcher(method, url, body, headers)
        return RawRecord(payload=text, url=url, status=status)

    def fetch(self, query: Any) -> list[RawRecord]:
        """Implementación base: GET a la query como URL."""
        return [self._request("GET", str(query))]


# ---------------------------------------------------------------------------
# OsvDepSource — consulta OSV.dev por vulnerabilidades de una dep PyPI
# ---------------------------------------------------------------------------

class OsvDepSource(HttpApiSource):
    """Consulta OSV.dev por vulnerabilidades de una dependencia PyPI.
    domain='security/cve'. Conocimiento de seguridad sobre las propias deps de Atlas."""

    _OSV_URL = "https://api.osv.dev/v1/query"

    def __init__(self, *, bridge: SSRFBridge | None = None, fetcher: Fetcher | None = None) -> None:
        super().__init__(source_id="osv.dev/pypi", domain="security/cve", bridge=bridge, fetcher=fetcher)

    def fetch(self, query: Any) -> list[RawRecord]:  # query = nombre de dep (str)
        dep_name = str(query)
        body = {"package": {"name": dep_name, "ecosystem": "PyPI"}}
        return [self._request("POST", self._OSV_URL, json_body=body)]


# ---------------------------------------------------------------------------
# McpKnowledgeSource — expone las tools MCP como artefacto de conocimiento
# ---------------------------------------------------------------------------

class McpKnowledgeSource:
    """Envuelve McpRegistry como KnowledgeSource (ADR-049 slice 4).

    NO gestiona lifecycle del registry (start/close son del orquestador).
    fetch() devuelve un RawRecord con JSON de las tools disponibles.
    domain='tools/mcp'; el SelfImprovementBridge ignora este dominio (safe).
    """

    def __init__(self, registry: "Any") -> None:
        self.source_id = "mcp/local"
        self.domain = "tools/mcp"
        self._registry = registry

    def fetch(self, query: "Any" = None) -> "list[RawRecord]":
        try:
            specs = self._registry.tool_specs()
            try:
                server_count = len(self._registry._configs)
            except Exception:
                server_count = 0
            payload = json.dumps({"tools": specs, "server_count": server_count})
            return [RawRecord(payload=payload, url="mcp://local", status=200)]
        except Exception as exc:  # noqa: BLE001
            return [RawRecord(payload=f"error:{exc}", url="mcp://local", status=-1)]
