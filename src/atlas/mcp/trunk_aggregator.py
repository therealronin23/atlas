"""
Atlas Core — TrunkAggregator: el tronco que frontea las raíces (línea B).

Un MCP único, CLASIFICADO por sector, con descubrimiento LAZY/jerárquico
(anti-kitchen-sink): el cliente ve primero los sectores (índice pequeño) y baja a
las tools de un sector solo cuando lo necesita. Concepto asimilado de
1mcp/MarimerLLC/metamcp, montado sobre NUESTRA base.

Capa NEUTRA: el `dispatcher` (que reenvía a la raíz real) se inyecta. En producción
lo provee `McpRegistry` (namespacing `mcp__<root>__<tool>` + Merkle + SentinelGate,
nuestro diferencial frente a magg/1mcp). Aquí no se sabe de transporte.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.trunk_manifest import RootSpec

Dispatcher = Callable[[str, dict[str, Any]], Any]


class TrunkAggregator:
    def __init__(
        self,
        *,
        catalog: list[CatalogEntry],
        roots: list[RootSpec],
        dispatcher: Dispatcher,
    ) -> None:
        self._roots = roots
        self._dispatcher = dispatcher
        # Mapa raíz → (sector, label, purpose) desde el catálogo (la clasificación).
        self._meta: dict[str, CatalogEntry] = {e.name: e for e in catalog}
        # Mapa tool → raíz (para el routing del dispatch).
        self._owner: dict[str, str] = {
            tool: root.name for root in roots for tool in root.tools
        }

    # -- Nivel 1: índice lazy de sectores (pequeño, sin schemas) -----------

    def sectors(self) -> list[dict[str, Any]]:
        agg: dict[str, dict[str, Any]] = {}
        for root in self._roots:
            entry = self._meta.get(root.name)
            sector = entry.sector if entry else "unclassified"
            label = entry.sector_label if entry else "Sin clasificar"
            bucket = agg.setdefault(
                sector, {"sector": sector, "label": label, "tool_count": 0}
            )
            bucket["tool_count"] += len(root.tools)
        return list(agg.values())

    # -- Nivel 2: drill-down a un sector ----------------------------------

    def tools_in(self, sector: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for root in self._roots:
            entry = self._meta.get(root.name)
            if (entry.sector if entry else "unclassified") != sector:
                continue
            purpose = entry.purpose if entry else ""
            for tool in root.tools:
                out.append({"name": tool, "root": root.name, "purpose": purpose})
        return out

    # -- Dispatch: enruta a la raíz dueña vía namespacing -----------------

    def invoke(self, tool: str, args: dict[str, Any]) -> Any:
        root = self._owner.get(tool)
        if root is None:
            raise KeyError(f"trunk: tool desconocida {tool!r}")
        return self._dispatcher(f"mcp__{root}__{tool}", args)
