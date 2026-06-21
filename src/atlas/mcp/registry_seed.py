"""
Atlas Core — Sembrado del catálogo desde el registro oficial MCP (C paso 4).

`registry.modelcontextprotocol.io` (ya en allowlist SSRF, ADR-039) → candidatos
para el catálogo, con PROCEDENCIA (fuente + fecha). Honesto: todo entra como
`candidato` y `uncategorized`; verificar (prove-it) y clasificar por sector son
pasos posteriores y explícitos. Fetcher inyectable → el acceso a red lo decide el
caller (sin red en tests).

Diseño: docs/design/mcp_trunk_portable.md + mcp_sector_architecture_audit.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.knowledge.sources import Fetcher, HttpApiSource, RawRecord
from atlas.security.ssrf_bridge import SSRFBridge

_HOST = "registry.modelcontextprotocol.io"


class RegistrySource(HttpApiSource):
    """Fuente del registro oficial MCP (`/v0/servers`)."""

    def __init__(self, *, fetcher: Fetcher | None = None, limit: int = 100) -> None:
        super().__init__(
            "mcp-registry",
            "mcp/registry",
            bridge=SSRFBridge(extra_allowed={_HOST}),
            fetcher=fetcher,
        )
        self._limit = limit

    def fetch(self, query: Any) -> list[RawRecord]:
        url = f"https://{_HOST}/v0/servers?limit={self._limit}"
        return [self._request("GET", url)]


def _transport_of(server: dict[str, Any]) -> str:
    if server.get("remotes"):
        return "http"
    if server.get("packages"):
        return "stdio"
    return ""


def registry_to_candidates(payload: dict[str, Any], *, source_url: str) -> list[dict[str, Any]]:
    """Mapea la respuesta del registro → entradas candidatas de catálogo, con
    procedencia. Sin clasificar (sector=uncategorized) hasta el triaje."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, Any]] = []
    for item in payload.get("servers", []):
        server = item.get("server", {})
        name = server.get("name")
        if not name:
            continue
        out.append({
            "name": name,
            "sector": "uncategorized",
            "kind": "mcp",
            "mode": "connected",
            "purpose": server.get("description", ""),
            "version": server.get("version", ""),
            "transport": _transport_of(server),
            "source": name,
            "install": "",
            "status": "candidato",
            "tags": [],
            "provenance": {"source": source_url, "fetched_at": fetched_at},
        })
    return out
