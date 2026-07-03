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
        dispatcher: Dispatcher,
        servers: dict[str, list[str]] | None = None,
        roots: list[RootSpec] | None = None,
        refresh: Callable[[str], dict[str, list[str]]] | None = None,
        is_read_only: Callable[[str], bool] | None = None,
    ) -> None:
        # `servers` = lo realmente conectado (server → tools), incl. externos. Si no
        # se da, se deriva de `roots` (native_roots) por conveniencia/tests.
        if servers is None:
            servers = {r.name: list(r.tools) for r in (roots or [])}
        self._servers = servers
        self._dispatcher = dispatcher
        # `refresh(tool)` = routing perezoso: ante un tool desconocido, spawnea/
        # descubre raíces externas y devuelve el mapa server → tools actualizado.
        self._refresh = refresh
        # `is_read_only(full_name)` = predicado ESTÁTICO (catálogo/config, nunca
        # juicio LLM — invariante D2) para `invoke_readonly`.
        self._is_read_only = is_read_only
        # Mapa server → entrada de catálogo (sector/label/purpose = la clasificación).
        self._meta: dict[str, CatalogEntry] = {e.name: e for e in catalog}
        # Mapa tool → server (para el routing del dispatch).
        self._owner: dict[str, str] = {
            tool: server for server, tools in servers.items() for tool in tools
        }

    # -- Nivel 1: índice lazy de sectores (pequeño, sin schemas) -----------

    def sectors(self) -> list[dict[str, Any]]:
        agg: dict[str, dict[str, Any]] = {}
        for server, tools in self._servers.items():
            entry = self._meta.get(server)
            sector = entry.sector if entry else "unclassified"
            label = entry.sector_label if entry else "Sin clasificar"
            bucket = agg.setdefault(
                sector, {"sector": sector, "label": label, "tool_count": 0}
            )
            bucket["tool_count"] += len(tools)
        return list(agg.values())

    # -- Nivel 2: drill-down a un sector ----------------------------------

    def tools_in(self, sector: str, subsector: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for server, tools in self._servers.items():
            entry = self._meta.get(server)
            if (entry.sector if entry else "unclassified") != sector:
                continue
            if subsector is not None and (entry.subsector if entry else "") != subsector:
                continue
            purpose = entry.purpose if entry else ""
            sub = entry.subsector if entry else ""
            for tool in tools:
                out.append({"name": tool, "root": server, "subsector": sub, "purpose": purpose})
        return out

    # -- Dispatch: enruta a la raíz dueña vía namespacing -----------------

    def invoke(self, tool: str, args: dict[str, Any]) -> Any:
        root = self._resolve_owner(tool)
        return self._dispatcher(f"mcp__{root}__{tool}", args)

    def invoke_readonly(self, tool: str, args: dict[str, Any]) -> Any:
        """Como `invoke`, pero SOLO despacha tools declaradas de lectura en el
        config de su raíz (read_only_tools — ADR-035 dec.5). Fail-closed: sin
        predicado, o tool no declarada, se rechaza. Permite al host marcar esta
        vía como 'read' sin abrir la puerta a mutaciones anidadas."""
        root = self._resolve_owner(tool)
        full = f"mcp__{root}__{tool}"
        if self._is_read_only is None or not self._is_read_only(full):
            raise PermissionError(
                f"trunk: {tool!r} no está declarada de solo lectura — usa trunk_invoke"
            )
        return self._dispatcher(full, args)

    def _resolve_owner(self, tool: str) -> str:
        root = self._owner.get(tool)
        if root is None and self._refresh is not None:
            # Routing perezoso: los MCP externos no están en el índice estático
            # hasta su primer spawn — refresh los descubre y reindexa.
            for server, tools in self._refresh(tool).items():
                self._servers.setdefault(server, tools)
                for t in tools:
                    self._owner.setdefault(t, server)
            root = self._owner.get(tool)
        if root is None:
            raise KeyError(f"trunk: tool desconocida {tool!r}")
        return root
