"""
Atlas Core — Shell FastMCP del TRONCO-AGREGADOR (línea B).

Expone una superficie META PEQUEÑA (anti-kitchen-sink): el cliente se conecta a
UN solo server (el tronco) y ve 3 tools de navegación lazy en vez de las N tools
de todas las raíces:
  - trunk_sectors()        → índice de sectores (nivel 1)
  - trunk_tools(sector)    → tools del sector (nivel 2, drill-down)
  - trunk_invoke(tool,args)→ ejecuta una tool, enrutada a su raíz dueña

SDK `mcp` opcional ([mcp]); import diferido. El dispatcher real (McpRegistry, con
Merkle + SentinelGate) se inyecta al construir el TrunkAggregator.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.mcp.trunk_aggregator import TrunkAggregator

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def build_trunk_server(agg: TrunkAggregator, *, name: str = "atlas-trunk") -> "FastMCP":
    """Servidor FastMCP que expone la fachada meta lazy del tronco."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def trunk_sectors() -> list[dict[str, Any]]:
        """Índice de sectores (nivel 1, pequeño): empieza SIEMPRE por aquí."""
        return agg.sectors()

    @server.tool()
    def trunk_tools(sector: str) -> list[dict[str, Any]]:
        """Tools de un sector (nivel 2): baja aquí solo cuando sabes el sector."""
        return agg.tools_in(sector)

    @server.tool()
    def trunk_invoke(tool: str, args: dict[str, Any] | None = None) -> Any:
        """Ejecuta una tool, enrutada a su raíz dueña (con audit/seguridad detrás)."""
        return agg.invoke(tool, args or {})

    return server
