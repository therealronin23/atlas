"""ADR-035 — cliente MCP: transporte stdio + registry E2E.

Usa el toy server ``tests/fixtures/mcp_echo_server.py`` (stdlib pura, sin
red) para ejercitar el handshake, ``tools/list``, ``tools/call`` y el
namespacing ``mcp__<server>__<tool>``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas.mcp.config import McpServerConfig, load_servers, save_servers
from atlas.mcp.registry import McpRegistry
from atlas.mcp.transport import McpProtocolError, StdioTransport


FIXTURE = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"


def _echo_cfg(**overrides) -> McpServerConfig:
    base = {
        "name": "echo",
        "cmd": [sys.executable, str(FIXTURE)],
        "read_only_tools": ["echo"],
    }
    base.update(overrides)
    return McpServerConfig(**base)


# ===========================================================================
# Transport
# ===========================================================================


def test_stdio_transport_initialize_and_list() -> None:
    t = StdioTransport(cmd=[sys.executable, str(FIXTURE)])
    try:
        result = t.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        })
        assert isinstance(result, dict)
        assert "protocolVersion" in result
        tools = t.request("tools/list", {})
        assert isinstance(tools, dict)
        names = [tool["name"] for tool in tools["tools"]]
        assert "echo" in names and "append_file" in names
    finally:
        t.close()


def test_stdio_transport_skips_out_of_band_notifications() -> None:
    """Si el server emite notificaciones intercaladas, el request las
    descarta y devuelve la respuesta correcta."""
    t = StdioTransport(
        cmd=[sys.executable, str(FIXTURE)],
        env={"ECHO_PREAMBLE": "1", "PATH": ""},
    )
    try:
        result = t.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        })
        assert isinstance(result, dict)
    finally:
        t.close()


def test_stdio_transport_server_dead_raises() -> None:
    t = StdioTransport(cmd=[sys.executable, "-c", "import sys; sys.exit(0)"])
    with pytest.raises(McpProtocolError):
        t.request("initialize", {})
    t.close()


def test_stdio_transport_times_out_on_silent_server() -> None:
    """ADR-035: un server que acepta el request pero nunca responde no
    bloquea el loop — ``timeout_seconds`` se aplica en la I/O."""
    t = StdioTransport(
        cmd=[sys.executable, "-c", "import sys, time; sys.stdin.readline(); time.sleep(30)"],
        timeout_seconds=0.3,
    )
    try:
        with pytest.raises(McpProtocolError, match="timed out"):
            t.request("initialize", {})
    finally:
        t.close()


def test_stdio_transport_starts_server_in_hardened_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakePipe:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _FakeProc:
        pid = 4242
        stdin = _FakePipe()
        stdout = _FakePipe()
        stderr = _FakePipe()

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            pass

    def _fake_popen(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr("atlas.mcp.transport.subprocess.Popen", _fake_popen)
    t = StdioTransport(cmd=["fake-mcp"])
    t.start()

    assert captured["kwargs"]["start_new_session"] is True
    assert callable(captured["kwargs"]["preexec_fn"])


# ===========================================================================
# Config / secrets
# ===========================================================================


def test_resolve_env_missing_secret_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_API_KEY", raising=False)
    cfg = McpServerConfig(
        name="x", cmd=["true"], env_passthrough=["FAKE_API_KEY"],
    )
    env, missing = cfg.resolve_env()
    assert missing == ["FAKE_API_KEY"]
    assert "FAKE_API_KEY" not in env


def test_resolve_env_does_not_propagate_host_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Por defecto solo PATH + env_extra + secretos declarados llegan al
    hijo. Mitiga 'credential theft from env vars'."""
    monkeypatch.setenv("SUPER_SECRET", "leaky")
    cfg = McpServerConfig(name="x", cmd=["true"], env_extra={"LANG": "C"})
    env, _ = cfg.resolve_env()
    assert "SUPER_SECRET" not in env
    assert env.get("LANG") == "C"


def test_load_servers_returns_empty_if_missing(tmp_path: Path) -> None:
    assert load_servers(tmp_path / "missing.json") == []


def test_load_servers_parses_json(tmp_path: Path) -> None:
    p = tmp_path / "servers.json"
    p.write_text(json.dumps([{
        "name": "demo",
        "cmd": ["echo", "hi"],
        "read_only_tools": ["look"],
        "enabled": False,
    }]))
    servers = load_servers(p)
    assert len(servers) == 1
    assert servers[0].name == "demo"
    assert servers[0].enabled is False
    assert servers[0].read_only_tools == ["look"]


def test_save_servers_roundtrips_through_load_servers(tmp_path: Path) -> None:
    p = tmp_path / "servers.json"
    cfgs = [
        McpServerConfig(
            name="demo",
            cmd=["echo", "hi"],
            read_only_tools=["look"],
            env_passthrough=["SOME_API_KEY"],
            enabled=False,
        ),
    ]
    save_servers(p, cfgs)
    reloaded = load_servers(p)
    assert len(reloaded) == 1
    assert reloaded[0].name == "demo"
    assert reloaded[0].env_passthrough == ["SOME_API_KEY"]
    assert reloaded[0].enabled is False


def test_save_servers_creates_parent_directory(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "servers.json"
    save_servers(p, [_echo_cfg()])
    assert p.exists()
    assert load_servers(p)[0].name == "echo"


# ===========================================================================
# Registry E2E
# ===========================================================================


def test_registry_lists_namespaced_tools() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        specs = reg.tool_specs()
        names = [s["function"]["name"] for s in specs]
        assert "mcp__echo__echo" in names
        assert "mcp__echo__append_file" in names
    finally:
        reg.close_all()


def test_registry_read_only_classification() -> None:
    """ADR-035 dec.5: mutate por defecto; allowlist marca lectura."""
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        assert reg.is_read_only("mcp__echo__echo") is True
        assert reg.is_read_only("mcp__echo__append_file") is False
        assert reg.is_read_only("mcp__nope__nope") is False
    finally:
        reg.close_all()


def test_registry_dispatch_echo_inline() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        out = reg.dispatch("mcp__echo__echo", json.dumps({"text": "hola"}))
        assert out == "hola"
    finally:
        reg.close_all()


def test_registry_dispatch_mutating_tool_actually_mutates(tmp_path: Path) -> None:
    reg = McpRegistry([_echo_cfg()])
    target = tmp_path / "out.txt"
    try:
        reg.start_all()
        out = reg.dispatch(
            "mcp__echo__append_file",
            {"path": str(target), "line": "uno"},
        )
        assert out == "ok"
        assert target.read_text() == "uno\n"
    finally:
        reg.close_all()


def test_registry_dispatch_unknown_returns_error() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        out = reg.dispatch("mcp__echo__no_such", "{}")
        assert out.startswith("error:")
    finally:
        reg.close_all()


def test_registry_unknown_tool_not_routed() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        assert reg.knows("mcp__echo__echo") is True
        assert reg.knows("mcp__other__x") is False
        out = reg.dispatch("mcp__other__x", "{}")
        assert "desconocida" in out
    finally:
        reg.close_all()


def test_registry_failed_server_does_not_block_others() -> None:
    """Un server que muere al inicio se ignora; el otro sigue funcionando."""
    bad = McpServerConfig(name="bad", cmd=[sys.executable, "-c", "import sys; sys.exit(1)"])
    reg = McpRegistry([bad, _echo_cfg()])
    try:
        reg.start_all()
        names = [s["function"]["name"] for s in reg.tool_specs()]
        assert any(n.startswith("mcp__echo__") for n in names)
        assert not any(n.startswith("mcp__bad__") for n in names)
    finally:
        reg.close_all()


# ===========================================================================
# Registro dinámico (hot add/remove)
# ===========================================================================


def test_add_server_hot() -> None:
    reg = McpRegistry([])
    try:
        reg.start_all()
        assert reg.tool_specs() == []
        status = reg.add_server(_echo_cfg())
        assert status.startswith("ok")
        assert reg.knows("mcp__echo__echo")
        assert reg.dispatch("mcp__echo__echo", json.dumps({"text": "hi"})) == "hi"
    finally:
        reg.close_all()


def test_add_server_duplicate_is_skipped() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        status = reg.add_server(_echo_cfg())
        assert status.startswith("skipped")
    finally:
        reg.close_all()


def test_remove_server_hot() -> None:
    reg = McpRegistry([_echo_cfg()])
    try:
        reg.start_all()
        assert reg.knows("mcp__echo__echo")
        assert reg.remove_server("echo") is True
        assert reg.knows("mcp__echo__echo") is False
        assert reg.knows("mcp__echo__append_file") is False
        assert reg.tool_specs() == []
        # idempotente: quitar lo ya quitado no rompe
        assert reg.remove_server("echo") is False
    finally:
        reg.close_all()


def test_add_server_persists_to_disk_and_survives_reload(tmp_path: Path) -> None:
    """2026-07-04: add_server() sin persist_path solo mutaba en memoria — una
    adopción aprobada por el decisor se evaporaba al reiniciar el daemon
    (load_servers() releía el mismo fichero de siempre y no veía nada nuevo).
    Con persist_path cableado, la config recién adoptada debe sobrevivir a un
    load_servers() fresco, como si fuera un reinicio real."""
    config_path = tmp_path / "mcp_servers.json"
    reg = McpRegistry([], persist_path=config_path)
    try:
        reg.start_all()
        status = reg.add_server(_echo_cfg())
        assert status.startswith("ok")
    finally:
        reg.close_all()

    reloaded = load_servers(config_path)
    assert [c.name for c in reloaded] == ["echo"]


def test_remove_server_persists_removal_to_disk(tmp_path: Path) -> None:
    """Simétrico al add: quitar un server (p.ej. undo de una adopción) debe
    quitarlo también del fichero, o reaparecería tras un reinicio pese a
    haberse deshecho en caliente."""
    config_path = tmp_path / "mcp_servers.json"
    reg = McpRegistry([_echo_cfg()], persist_path=config_path)
    try:
        reg.start_all()
        assert reg.remove_server("echo") is True
    finally:
        reg.close_all()

    assert load_servers(config_path) == []


def test_persist_path_none_keeps_old_in_memory_only_behavior() -> None:
    """Sin persist_path (default), add_server sigue funcionando exactamente
    como antes — no debe fallar por falta de un fichero de destino."""
    reg = McpRegistry([])
    try:
        reg.start_all()
        status = reg.add_server(_echo_cfg())
        assert status.startswith("ok")
    finally:
        reg.close_all()


def test_add_then_remove_then_readd() -> None:
    reg = McpRegistry([])
    try:
        reg.start_all()
        assert reg.add_server(_echo_cfg()).startswith("ok")
        assert reg.remove_server("echo") is True
        assert reg.add_server(_echo_cfg()).startswith("ok")
        assert reg.knows("mcp__echo__echo")
    finally:
        reg.close_all()
