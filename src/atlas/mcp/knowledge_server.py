"""
Atlas Core — Shell FastMCP de la raíz `knowledge-src` (MCP trunk portable, F3).

Traduce `KnowledgeTrunk` a un servidor MCP real: `wikipedia_lookup` (inspección
cruda) e `ingest_wikipedia` (run_mission → sustrato con procedencia).

SDK `mcp` opcional ([mcp]); import diferido. Honesto: procedencia, no verdad.

Diseño: docs/design/mcp_trunk_portable.md (F3).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.mcp.knowledge_trunk import KnowledgeTrunk

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def build_knowledge_server(trunk: KnowledgeTrunk, *, name: str = "atlas-knowledge") -> "FastMCP":
    """Servidor FastMCP con los tools de conocimiento libre + ingesta."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def wikipedia_lookup(title: str) -> list[dict[str, Any]]:
        """Consulta Wikipedia sin ingestar (payload + url + status)."""
        return trunk.wikipedia(title)

    @server.tool()
    def ingest_wikipedia(title: str, domain: str = "knowledge/wikipedia", goal: str = "") -> dict[str, Any]:
        """Ingesta un artículo al sustrato verificable con procedencia."""
        return trunk.ingest_wikipedia(title, domain=domain, goal=goal)

    @server.tool()
    def worldbank_lookup(country: str, indicator: str) -> list[dict[str, Any]]:
        """Consulta un indicador World Bank por país sin ingestar."""
        return trunk.worldbank(country, indicator)

    @server.tool()
    def ingest_worldbank(
        country: str, indicator: str, domain: str = "knowledge/worldbank", goal: str = ""
    ) -> dict[str, Any]:
        """Ingesta un indicador World Bank al sustrato con procedencia."""
        return trunk.ingest_worldbank(country, indicator, domain=domain, goal=goal)

    @server.tool()
    def ingest_open_meteo(latitude: float, longitude: float, goal: str = "") -> dict[str, Any]:
        """Ingesta el clima actual de unas coordenadas (Open-Meteo, sin auth)."""
        return trunk.ingest_open_meteo(latitude, longitude, goal=goal)

    @server.tool()
    def ingest_frankfurter(frm: str, to: str, goal: str = "") -> dict[str, Any]:
        """Ingesta un tipo de cambio (Frankfurter, sin auth) con procedencia."""
        return trunk.ingest_frankfurter(frm, to, goal=goal)

    return server


def serve(base_root: Path, *, name: str = "atlas-knowledge") -> None:
    """Entry stdio: monta la raíz knowledge-src sobre `base_root` y la sirve."""
    server = build_knowledge_server(KnowledgeTrunk(base_root), name=name)
    server.run()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("uso: python -m atlas.mcp.knowledge_server <base_root>")
    serve(Path(sys.argv[1]))
