"""
Tests del F2 del MCP trunk portable: la raíz `operating` — disciplina operativa
expuesta de forma portable. OPERATING LOOP + manías (AGENTS.md) y WORK_LEDGER.md
como RECURSOS que cualquier cliente extrae al arrancar (vía de enforcement
portable, más que un hook por-cliente); `sanitation_audit` como TOOL read-only.

Capa NEUTRA (`OperatingTrunk`): Python puro, sin MCP. El shell FastMCP encima.

Diseño: docs/design/mcp_trunk_portable.md (F2). Honesto: MCP NO puede IMPONER un
system prompt; estos recursos son advisory (el cliente decide cargarlos). El
franken-prompt por canal real queda fuera de F2.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _trunk() -> "OperatingTrunk":
    from atlas.mcp.operating_trunk import OperatingTrunk

    return OperatingTrunk(_repo_root())


# ---------------------------------------------------------------------------
# Recursos: AGENTS.md (operating loop + manías) y WORK_LEDGER.md
# ---------------------------------------------------------------------------


def test_agents_md_resource_has_operating_loop() -> None:
    text = _trunk().agents_md()
    assert "OPERATING LOOP" in text


def test_work_ledger_resource_has_state() -> None:
    text = _trunk().work_ledger()
    assert "WORK LEDGER" in text


def test_missing_repo_root_raises() -> None:
    from atlas.mcp.operating_trunk import OperatingTrunk

    trunk = OperatingTrunk(Path("/no/such/repo"))
    with pytest.raises(FileNotFoundError):
        trunk.agents_md()


# ---------------------------------------------------------------------------
# Tool: sanitation_audit (read-only; el radar del ciclo de saneamiento)
# ---------------------------------------------------------------------------


def test_sanitation_audit_returns_report() -> None:
    report = _trunk().sanitation_audit()
    assert "Auditoría de saneamiento" in report


# ---------------------------------------------------------------------------
# Shell FastMCP: recursos + tool montados como servidor MCP real.
# ---------------------------------------------------------------------------


def test_build_operating_server_registers_resource_and_tool() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.operating_server import build_operating_server

    server = build_operating_server(_trunk())
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert "sanitation_audit" in tools
    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert any("agents" in u for u in resources)
    assert any("ledger" in u for u in resources)
