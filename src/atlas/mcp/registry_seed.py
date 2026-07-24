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


def _first_package(server: dict[str, Any]) -> dict[str, Any] | None:
    packages = server.get("packages")
    return packages[0] if packages else None


def _first_remote_url(server: dict[str, Any]) -> str:
    """El campo ``name`` del registro (ej. 'ac.inference.sh/mcp') es solo un
    identificador estilo reverse-DNS -- NO el host real (que puede ser un
    dominio totalmente distinto). Sin esto no hay nada que contactar en la
    etapa 2B."""
    remotes = server.get("remotes")
    if not remotes:
        return ""
    return str(remotes[0].get("url", ""))


def _install_spec(pkg: dict[str, Any] | None) -> str:
    """``registry:identifier[==version]`` -- lo mínimo que un fetcher real
    necesita para saber QUÉ descargar (bloqueaba la etapa 2A de ADR-075 sin
    esto: antes ``install`` salía siempre vacío)."""
    if not pkg:
        return ""
    registry = pkg.get("registryType", "")
    identifier = pkg.get("identifier", "")
    if not registry or not identifier:
        return ""
    version = pkg.get("version", "")
    return f"{registry}:{identifier}=={version}" if version else f"{registry}:{identifier}"


_DEFAULT_SOURCE_URL = f"https://{_HOST}/v0/servers"


def reseed_candidates(*, source: RegistrySource | None = None) -> dict[str, Any]:
    """Pagina el registro oficial, dedup por nombre entre páginas, devuelve
    ``{'candidates': [...], 'pages_fetched': int}``.

    Misma lógica que ``scripts/mcp_seed_registry.py::main()`` de hoy, pero
    importable -- para que un tick del scheduler (A.2) la invoque sin pasar
    por un script CLI. Levanta ``RuntimeError`` si la primera página no
    responde 200 (nada que sembrar, y silenciarlo sería fingir éxito)."""
    src = source or RegistrySource()
    records = src.fetch(None)
    seen_names: set[str] = set()
    candidates: list[dict[str, Any]] = []
    pages_fetched = 0
    for rec in records:
        if rec.status != 200:
            break
        pages_fetched += 1
        for cand in registry_to_candidates(json.loads(rec.payload), source_url=_DEFAULT_SOURCE_URL):
            name = cand["name"]
            if name in seen_names:
                continue
            seen_names.add(name)
            candidates.append(cand)
    if pages_fetched == 0:
        first_status = records[0].status if records else "sin respuesta"
        raise RuntimeError(f"reseed: primera página del registro no accesible (status={first_status})")
    return {"candidates": candidates, "pages_fetched": pages_fetched}


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
        pkg = _first_package(server)
        repository = server.get("repository") or {}
        out.append({
            "name": name,
            "sector": "uncategorized",
            "kind": "mcp",
            "mode": "connected",
            "purpose": server.get("description", ""),
            "version": server.get("version", ""),
            "transport": _transport_of(server),
            "source": name,
            "install": _install_spec(pkg),
            "package_registry": pkg.get("registryType", "") if pkg else "",
            "package_identifier": pkg.get("identifier", "") if pkg else "",
            "repository_url": repository.get("url", ""),
            "remote_url": _first_remote_url(server),
            "status": "candidato",
            "tags": [],
            "provenance": {"source": source_url, "fetched_at": fetched_at},
        })
    return out
