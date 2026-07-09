"""Spawn perezoso de McpRegistry — ADR-035.

Verifica que el registry NO arranca servers al construirse y que
ensure_started / dispatch los arrancan on-demand usando un transport STUB
(sin procesos reales).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from atlas.mcp.config import McpServerConfig
from atlas.mcp.registry import McpRegistry
from atlas.mcp.transport import McpTransport


# ---------------------------------------------------------------------------
# Transport stub (sin procesos reales)
# ---------------------------------------------------------------------------

class _FakeTransport(McpTransport):
    """Transporte falso que responde a initialize/tools/list/tools/call."""

    def __init__(self, server_name: str, tools: list[str]) -> None:
        self._server = server_name
        self._tools = tools
        self.closed = False

    def request(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return {"protocolVersion": "2025-06-18", "capabilities": {}}
        if method == "tools/list":
            return {
                "tools": [
                    {"name": t, "description": f"tool {t}", "inputSchema": {"type": "object", "properties": {}}}
                    for t in self._tools
                ]
            }
        if method == "tools/call":
            tool = params.get("name")
            return {"content": [{"type": "text", "text": f"ok:{tool}"}]}
        return {}

    def notify(self, method: str, params: dict[str, Any]) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _make_registry(server_name: str = "x", tools: list[str] | None = None) -> tuple[McpRegistry, list[_FakeTransport]]:
    if tools is None:
        tools = ["sometool"]
    created: list[_FakeTransport] = []

    def factory(cfg: McpServerConfig) -> _FakeTransport:
        t = _FakeTransport(cfg.name, tools)
        created.append(t)
        return t

    cfg = McpServerConfig(name=server_name, cmd=["fake-cmd"])
    registry = McpRegistry([cfg], transport_factory=factory)
    return registry, created


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_spawn_on_construct() -> None:
    """Tras construir el registry SIN start_all, el server NO está arrancado."""
    registry, created = _make_registry()
    assert "x" not in registry._transports
    assert created == [], "factory no debe llamarse en __init__"


def test_ensure_started_arranca_server() -> None:
    """ensure_started('x') arranca el server y devuelve True."""
    registry, created = _make_registry()
    result = registry.ensure_started("x")
    assert result is True
    assert "x" in registry._transports
    assert len(created) == 1


def test_ensure_started_idempotente() -> None:
    """Llamar ensure_started dos veces no duplica el transporte."""
    registry, created = _make_registry()
    registry.ensure_started("x")
    registry.ensure_started("x")
    assert len(created) == 1


def test_ensure_started_server_desconocido() -> None:
    """ensure_started devuelve False si el server no tiene config."""
    registry, _ = _make_registry()
    result = registry.ensure_started("no_existe")
    assert result is False


def test_dispatch_arranca_on_demand() -> None:
    """dispatch('mcp__x__sometool', {}) arranca el server si no estaba y devuelve resultado."""
    registry, created = _make_registry()
    # El server aún no está arrancado.
    assert "x" not in registry._transports
    result = registry.dispatch("mcp__x__sometool", {})
    # Debe haber arrancado.
    assert "x" in registry._transports
    assert len(created) == 1
    # Y devolver el resultado de la tool.
    assert "ok:sometool" in result


def test_dispatch_tool_desconocida_tras_ensure() -> None:
    """Si el server arranca pero la tool no existe, dispatch devuelve error textual."""
    registry, _ = _make_registry(tools=["real_tool"])
    result = registry.dispatch("mcp__x__nonexistent", {})
    assert result.startswith("error:")


def test_ensure_started_server_disabled() -> None:
    """ensure_started retorna False para un server deshabilitado."""
    cfg = McpServerConfig(name="off", cmd=["x"], enabled=False)
    created: list[_FakeTransport] = []

    def factory(c: McpServerConfig) -> _FakeTransport:
        t = _FakeTransport(c.name, [])
        created.append(t)
        return t

    registry = McpRegistry([cfg], transport_factory=factory)
    result = registry.ensure_started("off")
    assert result is False
    assert created == []


def test_is_read_only_es_estatico_sin_arrancar_el_server() -> None:
    """is_read_only responde desde la config declarada ANTES del primer spawn.

    Con spawn perezoso + índice estático de raíces nativas, invoke_readonly
    consulta el predicado antes de que dispatch arranque el server; si el
    predicado dependiera del arranque, toda tool de lectura fallaría en frío
    (fail-closed convertido en fail-always)."""
    cfg = McpServerConfig(name="x", cmd=["fake-cmd"], read_only_tools=["ro_tool"])
    registry = McpRegistry([cfg], transport_factory=lambda c: _FakeTransport(c.name, ["ro_tool", "mut_tool"]))
    assert "x" not in registry._transports
    assert registry.is_read_only("mcp__x__ro_tool") is True
    assert registry.is_read_only("mcp__x__mut_tool") is False
    assert registry.is_read_only("mcp__desconocido__ro_tool") is False
    assert registry.is_read_only("sin_prefijo") is False
