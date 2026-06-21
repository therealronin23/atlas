"""
Atlas Core — Shell FastMCP de la raíz `operating` (MCP trunk portable, F2).

Traduce `OperatingTrunk` a un servidor MCP real: AGENTS.md y WORK_LEDGER.md como
RECURSOS (el cliente los lee al arrancar = vía de enforcement portable, más que un
hook por-cliente) y `sanitation_audit` como TOOL read-only.

SDK `mcp` opcional ([mcp]); import diferido. Honesto: recursos = advisory, no
imposición (ver design doc / docstring de OperatingTrunk).

Diseño: docs/design/mcp_trunk_portable.md (F2).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from atlas.mcp.operating_trunk import OperatingTrunk

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def build_operating_server(trunk: OperatingTrunk, *, name: str = "atlas-operating") -> "FastMCP":
    """Servidor FastMCP con los recursos operating + el tool sanitation_audit."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.resource("operating://agents", mime_type="text/markdown")
    def agents() -> str:
        """OPERATING LOOP + manías: cárgalo al arrancar (advisory, cross-tool)."""
        return trunk.agents_md()

    @server.resource("operating://ledger", mime_type="text/markdown")
    def ledger() -> str:
        """WORK_LEDGER: el estado vivo del '¿dónde estamos?'."""
        return trunk.work_ledger()

    @server.tool()
    def sanitation_audit() -> str:
        """Radar read-only del ciclo de saneamiento (no actúa; solo reporta)."""
        return trunk.sanitation_audit()

    return server


def serve(repo_root: Path, *, name: str = "atlas-operating") -> None:
    """Entry stdio: monta la raíz operating sobre `repo_root` y la sirve."""
    server = build_operating_server(OperatingTrunk(repo_root), name=name)
    server.run()


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    serve(root)
