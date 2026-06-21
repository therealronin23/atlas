"""
Tests del TRONCO-AGREGADOR (línea B): un MCP único que frontea las raíces,
CLASIFICADAS por sector, con descubrimiento LAZY/jerárquico (anti-kitchen-sink) —
el concepto asimilado de 1mcp/MarimerLLC/metamcp sobre NUESTRA base.

Capa NEUTRA (`TrunkAggregator`): Python puro. El dispatcher (que reenvía a la raíz
real) se INYECTA → testeable sin spawnear procesos; en producción lo provee
McpRegistry (Merkle + SentinelGate, nuestro diferencial).

Lazy: el cliente ve primero `sectors()` (índice pequeño), luego baja a
`tools_in(sector)` (drill-down). No ve las N tools de golpe.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CATALOG = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"


def _agg(dispatcher=None):
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots

    return TrunkAggregator(
        catalog=load_catalog(_CATALOG),
        roots=native_roots(),
        dispatcher=dispatcher or (lambda full_name, args: f"called:{full_name}"),
    )


# ---------------------------------------------------------------------------
# Índice lazy nivel 1: sectores (pequeño, sin schemas)
# ---------------------------------------------------------------------------


def test_sectors_groups_live_roots_by_catalog_sector() -> None:
    sectors = {s["sector"]: s for s in _agg().sectors()}
    # Las raíces vivas se agrupan por su sector del catálogo.
    assert "operating" in sectors
    assert "memory-knowledge" in sectors
    # operating solo tiene atlas-operating (1 tool: sanitation_audit)
    assert sectors["operating"]["tool_count"] == 1
    # cada sector trae label + cuenta, NO los schemas (lazy)
    assert sectors["operating"]["label"]
    assert "tools" not in sectors["operating"]


# ---------------------------------------------------------------------------
# Índice lazy nivel 2: drill-down a un sector
# ---------------------------------------------------------------------------


def test_tools_in_sector_returns_tools_with_root_and_purpose() -> None:
    tools = _agg().tools_in("operating")
    names = {t["name"] for t in tools}
    assert "sanitation_audit" in names
    san = next(t for t in tools if t["name"] == "sanitation_audit")
    assert san["root"] == "atlas-operating"
    assert san["purpose"]  # purpose del catálogo, para guiar el routing


def test_tools_in_unknown_sector_is_empty() -> None:
    assert _agg().tools_in("no-such-sector") == []


# ---------------------------------------------------------------------------
# Dispatch: enruta a la raíz correcta vía namespacing mcp__<root>__<tool>
# ---------------------------------------------------------------------------


def test_invoke_routes_to_owning_root() -> None:
    seen: list[tuple[str, dict]] = []
    agg = _agg(dispatcher=lambda full_name, args: seen.append((full_name, args)) or "ok")
    out = agg.invoke("recall", {"query": "x"})
    assert out == "ok"
    assert seen == [("mcp__atlas-memory__recall", {"query": "x"})]


def test_invoke_unknown_tool_raises() -> None:
    with pytest.raises(KeyError):
        _agg().invoke("nope", {})


# ---------------------------------------------------------------------------
# Shell FastMCP del tronco: superficie PEQUEÑA (3 tools meta), no las N raíz
# ---------------------------------------------------------------------------


def test_build_trunk_server_exposes_small_meta_surface() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.trunk_server import build_trunk_server

    server = build_trunk_server(_agg())
    names = {t.name for t in asyncio.run(server.list_tools())}
    # Anti-kitchen-sink: el cliente ve la fachada meta, no las 8 tools de raíz.
    assert {"trunk_sectors", "trunk_tools", "trunk_invoke"} <= names
    assert "recall" not in names
