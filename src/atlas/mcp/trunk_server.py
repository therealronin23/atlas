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

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.mcp.config import McpServerConfig
from atlas.mcp.trunk_aggregator import TrunkAggregator
from atlas.mcp.trunk_manifest import native_roots

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def root_configs(
    *, save_dir: Path, repo_root: Path, python: str | None = None
) -> list[McpServerConfig]:
    """McpServerConfig por raíz nativa: el tronco las spawnea como hijos stdio.
    El save (memoria/knowledge) en la capa neutra; operating apunta al repo."""
    exe = python if python is not None else sys.executable
    arg_for = {
        "db": str(Path(save_dir) / "memory.db"),
        "repo": str(repo_root),
        "base": str(Path(save_dir) / "kb"),
    }
    return [
        McpServerConfig(
            name=root.name,
            cmd=[exe, "-m", root.module, arg_for[root.arg_kind]],
            # recall/lookup/audit son de lectura; el resto mutan (HITL).
            read_only_tools=[t for t in root.tools if t.startswith(("recall", "wikipedia_lookup", "worldbank_lookup", "sanitation"))],
        )
        for root in native_roots()
    ]


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


def serve(*, save_dir: Path, repo_root: Path, name: str = "atlas-trunk") -> None:
    """Entry stdio del tronco: arranca un McpRegistry sobre las 3 raíces (Merkle +
    SentinelGate), las frontea con descubrimiento lazy por sector, y sirve UNA
    conexión. El cliente se conecta SOLO aquí."""
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.registry import McpRegistry

    registry = McpRegistry(root_configs(save_dir=save_dir, repo_root=repo_root))
    registry.start_all()
    catalog_path = Path(repo_root) / "docs" / "design" / "mcp_catalog.yaml"
    agg = TrunkAggregator(
        catalog=load_catalog(catalog_path),
        roots=native_roots(),
        dispatcher=registry.dispatch,
    )
    server = build_trunk_server(agg, name=name)
    try:
        server.run()
    finally:
        registry.close_all()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("uso: python -m atlas.mcp.trunk_server <save_dir> <repo_root>")
    serve(save_dir=Path(sys.argv[1]), repo_root=Path(sys.argv[2]))
