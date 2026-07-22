"""
Tests del F4 del MCP trunk portable: agregación (una conexión) + instalador.

Dos piezas:
- TrunkManifest: declara las raíces nativas (memory/operating/knowledge) y emite
  una config de cliente MCP unificada → "el tronco = una conexión". Mide el
  overhead de superficie (cuántas tools ve el cliente; anti-kitchen-sink).
- installer: lee el catálogo (docs/design/mcp_catalog.md), reporta por estado e
  instala SOLO lo `verificado` (nunca candidatos: wire-before-claim).

Diseño: docs/design/mcp_trunk_portable.md (F4) + docs/design/mcp_catalog.md.
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# TrunkManifest: agregación de raíces nativas en una sola config de cliente
# ---------------------------------------------------------------------------


def test_native_roots_are_the_four_built() -> None:
    from atlas.mcp.trunk_manifest import native_roots

    names = {r.name for r in native_roots()}
    assert names == {"atlas-memory", "atlas-operating", "atlas-knowledge", "atlas-graph"}


def test_client_config_lists_every_native_root_with_a_launch_command() -> None:
    from atlas.mcp.trunk_manifest import client_config

    cfg = client_config(
        memory_db=Path("/save/memory.db"),
        repo_root=Path("/repo"),
        knowledge_base=Path("/save/kb"),
    )
    servers = cfg["mcpServers"]
    assert set(servers) == {"atlas-memory", "atlas-operating", "atlas-knowledge", "atlas-graph"}
    mem = servers["atlas-memory"]
    assert mem["command"]  # un ejecutable
    assert "atlas.mcp.memory_server" in mem["args"]
    assert "/save/memory.db" in mem["args"]
    # atlas-graph recibe repo_root para contrastar frescura con HEAD; la BD
    # sigue resolviéndose mediante DEFAULT_GRAPH_DB.
    graph = servers["atlas-graph"]
    assert graph["args"] == ["-m", "atlas.mcp.graph_server", "/repo"]


def test_tool_overhead_is_small_anti_kitchen_sink() -> None:
    from atlas.mcp.trunk_manifest import tool_overhead

    # Superficie PEQUEÑA: las 4 raíces juntas exponen pocas tools (no 200).
    # 25 desde d39782c8 (2026-07-16, F3 cerrada): graph_communities +
    # graph_semantic_neighbors añadidas a atlas-graph (9->11 tools), commit
    # que olvidó subir este umbral — quedó roto en silencio 6 días hasta que
    # F2.6 corrió la suite completa (2026-07-22). Cada tool nueva real debe
    # subir este número A PROPÓSITO, en el mismo commit que la añade.
    assert tool_overhead() <= 25


# ---------------------------------------------------------------------------
# Installer: parsea el catálogo y respeta wire-before-claim
# NOTA: el catálogo + instalable se prueban ahora sobre la fuente ESTRUCTURADA
# (YAML) en tests/test_mcp_catalog_structured.py; el parser de tabla markdown
# (atlas.mcp.installer) fue retirado al quedar superado por atlas.mcp.catalog.

# ---------------------------------------------------------------------------
# Prueba real "una conexión": cada raíz de la config unificada arranca y expone
# sus tools declaradas (la config del manifest es fiel y lanzable).
# ---------------------------------------------------------------------------


def test_every_root_in_unified_config_launches_and_exposes_its_tools(tmp_path: Path) -> None:
    import pytest

    pytest.importorskip("mcp")
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from atlas.mcp.trunk_manifest import client_config, native_roots

    repo_root = Path(__file__).resolve().parent.parent
    cfg = client_config(
        memory_db=tmp_path / "memory.db",
        repo_root=repo_root,
        knowledge_base=tmp_path / "kb",
    )["mcpServers"]
    declared = {r.name: set(r.tools) for r in native_roots()}

    async def _tools_of(name: str) -> set[str]:
        spec = cfg[name]  # type: ignore[index]
        params = StdioServerParameters(command=spec["command"], args=spec["args"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return {t.name for t in listed.tools}

    for name, expected in declared.items():
        got = asyncio.run(_tools_of(name))
        assert expected <= got, f"{name}: faltan tools {expected - got}"
