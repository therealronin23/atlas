"""
Atlas Core — El catálogo del tronco como RESOURCES MCP (índice + detalle).

Hueco #1 de `docs/design/mcp_six_primitives_audit.md`: hoy el catálogo se navega
solo por tool-calls (queman un turno por consulta). Estas funciones puras lo
serializan para exponerlo como Resources MCP (el "JSON índice" del usuario):

  - `manifest_json`  → índice LIGERO: nombres + 4 ejes de estado (status, kind,
    domain, subsector, mode) + summary + `fresh` (hash de change-detection).
  - `item_detail`    → el `CatalogEntry` COMPLETO de un item (kind/name), bajo demanda.

Sin dependencia de MCP: el cableado FastMCP vive en `trunk_server.py`. Diseño:
`docs/superpowers/specs/2026-06-25-catalog-resources-design.md`.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlas.mcp.catalog import CatalogEntry


def entry_id(entry: "CatalogEntry") -> str:
    """Id estable de un item del catálogo: ``kind/name`` (los items se identifican
    por kind+name en todo el catálogo, ver `dedupe_by_kind_name`)."""
    return f"{entry.kind}/{entry.name}"


def manifest_hash(entries: "list[CatalogEntry]") -> str:
    """Hash sha256[:16] de los pares (kind,name,status,mode) ORDENADOS.

    Cambia cuando el catálogo cambia de contenido relevante (alta/baja de items o
    cambio de estado/modo) e ignora el orden de la lista. Permite change-detection
    en el cliente sin push de subscriptions (que es follow-up)."""
    h = hashlib.sha256()
    for e in sorted(entries, key=lambda x: (x.kind, x.name)):
        h.update(f"{e.kind}\x1f{e.name}\x1f{e.status}\x1f{e.mode}\x1e".encode("utf-8"))
    return h.hexdigest()[:16]


def manifest_json(entries: "list[CatalogEntry]") -> str:
    """Índice LIGERO del catálogo como JSON (indent 2, utf-8).

    Estructura: ``{summary, fresh, items[]}`` donde cada item lleva los 4 ejes que
    el usuario pidió como 'etiqueta de estado': status · kind · domain (=sector) +
    subsector · mode. Sin prosa (eso va al detalle `item_detail`)."""
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for e in entries:
        by_status[e.status] = by_status.get(e.status, 0) + 1
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        items.append(
            {
                "id": entry_id(e),
                "name": e.name,
                "status": e.status,
                "kind": e.kind,
                "domain": e.sector,
                "subsector": e.subsector,
                "mode": e.mode,
            }
        )
    payload = {
        "summary": {"total": len(items), "by_status": by_status, "by_kind": by_kind},
        "fresh": manifest_hash(entries),
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def item_detail(entries: "list[CatalogEntry]", item_id: str) -> str | None:
    """Detalle COMPLETO de un item (todos los campos del `CatalogEntry`) como JSON,
    o ``None`` si no existe. ``item_id`` = ``"kind/name"`` (ver `entry_id`)."""
    for e in entries:
        if entry_id(e) == item_id:
            detail = {
                "id": item_id,
                "name": e.name,
                "kind": e.kind,
                "status": e.status,
                "mode": e.mode,
                "domain": e.sector,
                "domain_label": e.sector_label,
                "subsector": e.subsector,
                "purpose": e.purpose,
                "source": e.source,
                "install": e.install,
                "tags": list(e.tags),
                "phase": e.phase,
                "version": e.version,
                "license": e.license,
                "trust": e.trust,
                "transport": e.transport,
            }
            return json.dumps(detail, ensure_ascii=False, indent=2)
    return None
