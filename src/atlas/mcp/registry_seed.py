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

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from atlas.knowledge.sources import Fetcher, HttpApiSource, RawRecord
from atlas.security.ssrf_bridge import SSRFBridge

_HOST = "registry.modelcontextprotocol.io"


class RegistrySource(HttpApiSource):
    """Fuente del registro oficial MCP (`/v0/servers`).

    Pagina de verdad (verificado en vivo 2026-07-23: el registro real supera
    las 400 entradas con `metadata.nextCursor`; sin paginar, el sembrado se
    quedaba para siempre con solo la primera página de 100). ``max_pages``
    es un tope de seguridad -- un registro (o un bug) que nunca deja de dar
    cursor no debe colgar el sembrador indefinidamente.
    """

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        limit: int = 100,
        max_pages: int = 50,
    ) -> None:
        super().__init__(
            "mcp-registry",
            "mcp/registry",
            bridge=SSRFBridge(extra_allowed={_HOST}),
            fetcher=fetcher,
        )
        self._limit = limit
        self._max_pages = max_pages

    def fetch(self, query: Any) -> list[RawRecord]:
        records: list[RawRecord] = []
        cursor: str | None = None
        for _ in range(self._max_pages):
            url = f"https://{_HOST}/v0/servers?limit={self._limit}"
            if cursor:
                url += f"&cursor={quote(cursor, safe='')}"
            rec = self._request("GET", url)
            records.append(rec)
            if rec.status != 200:
                break
            try:
                payload = json.loads(rec.payload)
            except json.JSONDecodeError:
                break
            cursor = (payload.get("metadata") or {}).get("nextCursor") or None
            if not cursor:
                break
        return records


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
