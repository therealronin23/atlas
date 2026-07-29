"""Spawn perezoso de McpRegistry — ADR-035.

Verifica que el registry NO arranca servers al construirse y que
ensure_started / dispatch los arrancan on-demand usando un transport STUB
(sin procesos reales).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas.mcp.config import McpServerConfig
from atlas.mcp.registry import McpRegistry
from atlas.mcp.transport import McpTransport
from atlas.security.sentinel_gate import SentinelGate


_REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_configured_audit_records_start_request_before_transport_creation() -> None:
    """Catches moving the audit after the external process boundary."""
    events: list[str] = []

    def audit(**kwargs: object) -> object:
        events.append(str(kwargs["action"]))
        return object()

    def factory(cfg: McpServerConfig) -> _FakeTransport:
        events.append("spawn")
        return _FakeTransport(cfg.name, ["tool"])

    registry = McpRegistry(
        [McpServerConfig(name="x", cmd=["fake"])],
        transport_factory=factory,
        merkle_log=audit,
    )

    registry.start_all()

    assert events.index("mcp.server_start_requested") < events.index("spawn")


def test_configured_pre_spawn_audit_failure_blocks_transport_creation() -> None:
    """A configured but broken evidence boundary cannot degrade to execution."""
    spawned: list[str] = []

    def audit(**kwargs: object) -> object:
        if kwargs["action"] == "mcp.server_start_requested":
            raise RuntimeError("merkle unavailable")
        return object()

    def factory(cfg: McpServerConfig) -> _FakeTransport:
        spawned.append(cfg.name)
        return _FakeTransport(cfg.name, ["tool"])

    registry = McpRegistry(
        [McpServerConfig(name="x", cmd=["fake"])],
        transport_factory=factory,
        merkle_log=audit,
    )

    registry.start_all()

    assert spawned == []
    assert registry.tool_specs() == []


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


def test_is_read_only_verifies_the_server_before_trusting_config() -> None:
    """La primera consulta arranca y descubre la tool antes de llamarla read."""
    cfg = McpServerConfig(name="x", cmd=["fake-cmd"], read_only_tools=["ro_tool"])
    registry = McpRegistry([cfg], transport_factory=lambda c: _FakeTransport(c.name, ["ro_tool", "mut_tool"]))
    assert "x" not in registry._transports
    assert registry.is_read_only("mcp__x__ro_tool") is True
    assert "x" in registry._transports
    assert registry.is_read_only("mcp__x__mut_tool") is False
    assert registry.is_read_only("mcp__desconocido__ro_tool") is False
    assert registry.is_read_only("sin_prefijo") is False


def test_sentinel_tier_overrides_false_read_only_claim(tmp_path: Path) -> None:
    cfg = McpServerConfig(
        name="atlas-memory",
        cmd=[sys.executable, "-m", "atlas.mcp.memory_server", str(tmp_path / "x.db")],
        cwd=str(_REPO_ROOT),
        read_only_tools=["fetch_url"],
    )
    registry = McpRegistry(
        [cfg],
        transport_factory=lambda candidate: _FakeTransport(
            candidate.name, ["fetch_url"]
        ),
        sentinel=SentinelGate(tmp_path / "sentinel"),
    )

    assert registry.is_read_only("mcp__atlas-memory__fetch_url") is False
    assert "atlas-memory" in registry._transports


def test_duplicate_config_names_never_spawn_but_unique_config_does() -> None:
    created: list[str] = []

    def factory(cfg: McpServerConfig) -> _FakeTransport:
        created.append(cfg.name)
        return _FakeTransport(cfg.name, ["x"])

    registry = McpRegistry(
        [
            McpServerConfig(name="dup", cmd=["first"]),
            McpServerConfig(name="dup", cmd=["second"]),
            McpServerConfig(name="unique", cmd=["third"]),
        ],
        transport_factory=factory,
    )

    registry.start_all()

    assert created == ["unique"]
    assert registry.knows("mcp__unique__x")
    assert not registry.knows("mcp__dup__x")


def test_namespace_delimiter_in_server_name_is_rejected() -> None:
    created: list[str] = []
    registry = McpRegistry(
        [McpServerConfig(name="a__b", cmd=["fake"])],
        transport_factory=lambda cfg: created.append(cfg.name),  # type: ignore[arg-type]
    )

    registry.start_all()

    assert created == []


def test_different_config_cannot_reuse_existing_server_name() -> None:
    original = McpServerConfig(name="same", cmd=["original"])
    created: list[list[str]] = []
    registry = McpRegistry(
        [original],
        transport_factory=lambda cfg: (
            created.append(cfg.cmd) or _FakeTransport(cfg.name, ["x"])
        ),
    )

    status = registry.add_server(McpServerConfig(name="same", cmd=["different"]))

    assert status.startswith("vetoed:")
    assert created == []


class _InvalidListTransport(_FakeTransport):
    def __init__(self, payload: Any) -> None:
        super().__init__("invalid", [])
        self._payload = payload

    def request(self, method: str, params: dict[str, Any]) -> Any:
        if method == "tools/list":
            return self._payload
        return super().request(method, params)


@pytest.mark.parametrize(
    "payload",
    [
        {"tools": "not-a-list"},
        {"tools": [{"name": "a__b", "inputSchema": {"type": "object"}}]},
        {"tools": [{"name": "x", "inputSchema": "not-a-schema"}]},
        {
            "tools": [
                {"name": "dup", "inputSchema": {"type": "object"}},
                {"name": "dup", "inputSchema": {"type": "object"}},
            ]
        },
    ],
)
def test_malformed_tool_surface_closes_transport(payload: Any) -> None:
    created: list[_InvalidListTransport] = []

    def factory(cfg: McpServerConfig) -> _InvalidListTransport:
        transport = _InvalidListTransport(payload)
        created.append(transport)
        return transport

    registry = McpRegistry(
        [McpServerConfig(name="invalid", cmd=["fake"])],
        transport_factory=factory,
    )

    registry.start_all()

    assert created[0].closed is True
    assert registry.tool_specs() == []
    assert "invalid" not in registry._transports


class TestAdoptionStartFailureBackoff:
    """2026-07-10: el lazo de adopción re-spawneaba el mismo candidato roto en
    cada pasada (ai.agenttrust sin API key: 530 stacktraces en .atlas.err).
    N fallos de arranque → skip persistente auditado; un arranque OK limpia."""

    def _registry(self, tmp_path, *, boom: bool):
        calls: list[str] = []

        def factory(cfg: McpServerConfig) -> _FakeTransport:
            calls.append(cfg.name)
            if boom:
                raise ConnectionError("muere al arrancar")
            return _FakeTransport(cfg.name, ["t"])

        cfg = McpServerConfig(name="roto", cmd=["fake"])
        reg = McpRegistry(
            [cfg], transport_factory=factory,
            persist_path=tmp_path / "mcp_servers.json",
        )
        return reg, cfg, calls

    def test_three_failures_then_persistent_skip(self, tmp_path) -> None:
        reg, cfg, calls = self._registry(tmp_path, boom=True)
        for _ in range(3):
            assert reg.add_server(cfg).startswith("error:")
        status = reg.add_server(cfg)
        assert status.startswith("skipped:")
        assert "backoff" in status
        assert len(calls) == 3  # el 4º intento NO spawneó

        # El backoff sobrevive a un registry nuevo (persistente).
        reg2, cfg2, calls2 = self._registry(tmp_path, boom=False)
        assert reg2.add_server(cfg2).startswith("skipped:")
        assert calls2 == []

    def test_successful_start_clears_counter(self, tmp_path) -> None:
        reg, cfg, calls = self._registry(tmp_path, boom=True)
        reg.add_server(cfg)
        reg.add_server(cfg)  # 2 fallos, aún bajo el umbral
        reg_ok, cfg_ok, _ = self._registry(tmp_path, boom=False)
        assert reg_ok.add_server(cfg_ok).startswith("ok:")
        assert reg_ok._load_start_failures() == {}


def test_start_one_skips_when_declared_env_missing(monkeypatch, tmp_path) -> None:
    """Fail-fast pre-spawn: secretos declarados ausentes → no se spawnea
    (antes: el hijo moría con stacktrace y se reintentaba para siempre)."""
    monkeypatch.delenv("SECRETO_QUE_NO_EXISTE", raising=False)
    calls: list[str] = []

    def factory(cfg: McpServerConfig) -> _FakeTransport:
        calls.append(cfg.name)
        return _FakeTransport(cfg.name, ["t"])

    cfg = McpServerConfig(
        name="sin-secreto", cmd=["fake"], env_passthrough=["SECRETO_QUE_NO_EXISTE"],
    )
    registry = McpRegistry([cfg], transport_factory=factory)
    registry.ensure_started("sin-secreto")
    assert calls == []  # nunca llegó a spawnearse
    assert "sin-secreto" not in registry._transports
