"""
Atlas Core — Shell FastMCP de la raíz `engineering` (MCP trunk portable, F1).

Traduce `EngineeringTrunk` a un servidor MCP real. Expone lecturas de hallazgos,
hipótesis y diagnóstico.

SDK `mcp` opcional ([mcp]); import diferido.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.mcp.engineering_trunk import EngineeringTrunk

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def build_engineering_server(trunk: EngineeringTrunk, *, name: str = "atlas-engineering") -> "FastMCP":
    """Servidor FastMCP con los tools de ingeniería."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def engineering_read_findings() -> list[dict[str, Any]]:
        """Lee los hallazgos recientes del sistema de ingeniería."""
        return trunk.read_findings()

    @server.tool()
    def engineering_generate_hypotheses(path: str) -> dict[str, Any]:
        """Hipótesis combinadas (Grafo, Historia, Memoria) para una ruta
        repo-relativa, p. ej. `src/atlas/core/orchestrator.py`."""
        return trunk.generate_hypotheses(path)

    @server.tool()
    def engineering_impacted_tests(changed_files: list[str]) -> list[str]:
        """Descubre los tests afectados por una lista de ficheros modificados."""
        return trunk.get_impacted_tests(changed_files)

    return server


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python -m atlas.mcp.engineering_server <repo_root>", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(sys.argv[1]).resolve()
    server = build_engineering_server(EngineeringTrunk(repo_root), name="atlas-engineering")
    server.run()
