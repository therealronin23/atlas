"""
Atlas Core — La "mesa de trabajo" (SP-A) como RESOURCES MCP (índice unificado).

Une en un solo manifiesto las 4 fuentes de estado que hoy se consultan por
separado (catálogo, lecciones, backlog, memoria) para que el cliente MCP tenga
un único punto de entrada barato (Resources, no tool-calls) al estado del
sistema. Sigue el mismo patrón que `catalog_resources.py`:

  - `workbench_hash`          → hash combinado de las 4 fuentes, para
    change-detection en el cliente (cambia si cambia CUALQUIERA de ellas).
  - `workbench_manifest_json` → el manifiesto completo (summary de cada
    fuente + `fresh` + el índice ligero de backlog pendiente).

Sin dependencia de MCP: el cableado FastMCP vive en `trunk_server.py`.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from atlas.mcp import catalog_resources

if TYPE_CHECKING:
    from atlas.core.self_maintenance.backlog import BacklogItem
    from atlas.mcp.catalog import CatalogEntry

from atlas.core.self_maintenance.backlog import backlog_summary


def workbench_hash(
    catalog_entries: "list[CatalogEntry]",
    lesson_stats: dict[str, Any],
    backlog_items: "list[BacklogItem]",
    memory_count: int,
) -> str:
    """Hash sha256[:16] combinado de las 4 fuentes de la mesa de trabajo.

    Cambia si cambia CUALQUIERA de: el catálogo (misma lógica que
    `catalog_resources.manifest_hash`), el total de lecciones, el conteo de
    backlog por status, o el conteo de memoria."""
    h = hashlib.sha256()
    h.update(catalog_resources.manifest_hash(catalog_entries).encode("utf-8"))
    h.update(b"\x1e")
    h.update(str(lesson_stats["total"]).encode("utf-8"))
    h.update(b"\x1e")
    backlog_by_status = backlog_summary(backlog_items)["by_status"]
    for status in sorted(backlog_by_status):
        h.update(f"{status}\x1f{backlog_by_status[status]}\x1e".encode("utf-8"))
    h.update(b"\x1e")
    h.update(str(memory_count).encode("utf-8"))
    return h.hexdigest()[:16]


def workbench_manifest_json(
    catalog_entries: "list[CatalogEntry]",
    lesson_store: Any,
    backlog_items: "list[BacklogItem]",
    memory_count: int,
) -> str:
    """Manifiesto unificado de la mesa de trabajo como JSON (indent 2, utf-8).

    Estructura: ``{summary: {catalog, lessons, backlog, memory}, fresh,
    backlog_top_pending}``. El detalle por fuente sigue viviendo en sus
    propios Resources (`catalog_resources.item_detail`, etc.); esto es solo
    el índice para saber DÓNDE mirar."""
    catalog_summary = json.loads(catalog_resources.manifest_json(catalog_entries))["summary"]
    lesson_stats = lesson_store.stats()
    backlog = backlog_summary(backlog_items)
    payload = {
        "summary": {
            "catalog": catalog_summary,
            "lessons": lesson_stats,
            "backlog": {"total": backlog["total"], "by_status": backlog["by_status"]},
            "memory": {"count": memory_count},
        },
        "fresh": workbench_hash(catalog_entries, lesson_stats, backlog_items, memory_count),
        "backlog_top_pending": backlog["top_pending"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
