"""Tests Pieza 2c — spawn MCP trial + saneamiento graduado."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atlas.mcp.spawn_trial import (
    SpawnTrial,
    build_mcp_bwrap_argv,
    graduated_quarantine,
    is_atlas_native_module,
    probe_mcp_stdio,
    requires_network_bootstrap,
)
from atlas.mcp.trial_gate import TrialGate
from tests.test_trial_gate import _entry

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mcp_echo_server.py"


class _FakeTransport:
    def __init__(self, cmd: list[str], env: dict[str, str] | None) -> None:
        self._cmd = cmd
        self.closed = False

    def start(self) -> None:
        return None

    def request(self, method: str, params: dict | None = None) -> dict:
        if method == "initialize":
            return {"protocolVersion": "2025-06-18", "capabilities": {}}
        if method == "tools/list":
            return {"tools": [{"name": "echo"}, {"name": "append_file"}]}
        return {}

    def notify(self, method: str, params: dict | None = None) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_requires_network_bootstrap() -> None:
    assert requires_network_bootstrap(["npx", "-y", "pkg"]) is True
    assert requires_network_bootstrap([sys.executable, "-m", "atlas.mcp.memory_server"]) is False


def test_is_atlas_native_module() -> None:
    assert is_atlas_native_module([sys.executable, "-m", "atlas.mcp.memory_server", "/tmp/x"])
    assert is_atlas_native_module(["npx", "foo"]) is False


def test_probe_mcp_stdio_with_fake_transport() -> None:
    result = probe_mcp_stdio(
        ["fake"],
        transport_factory=lambda c, e: _FakeTransport(c, e),
    )
    assert result.ok is True
    assert result.tool_count == 2


def test_probe_mcp_stdio_live_echo() -> None:
    if not FIXTURE.is_file():
        pytest.skip("fixture missing")
    result = probe_mcp_stdio([sys.executable, str(FIXTURE)], timeout_seconds=10.0)
    assert result.ok is True
    assert result.tool_count == 2


def test_spawn_trial_skips_npx() -> None:
    trial = SpawnTrial()
    result = trial.probe_cmd(["npx", "-y", "@modelcontextprotocol/server-everything"])
    assert result.skipped is True
    assert "red" in result.reason


def test_graduated_quarantine_supply_chain() -> None:
    q = graduated_quarantine(name="x", kind="mcp", reason="metacaracter de shell")
    assert q is not None
    assert q.action == "quarantine"


def test_graduated_quarantine_retry_on_timeout() -> None:
    q = graduated_quarantine(name="x", kind="mcp", reason="spawn falló: timeout")
    assert q is not None
    assert q.action == "retry"


def test_trial_gate_mcp_with_spawn_fake() -> None:
    spawn = SpawnTrial(transport_factory=lambda c, e: _FakeTransport(c, e))
    gate = TrialGate(spawn_trial=spawn)
    result = gate.trial(
        _entry(
            kind="mcp",
            mode="connected",
            name="echo",
            install=f"{sys.executable} {FIXTURE}",
        )
    )
    assert result.passed is True
    assert "spawn OK" in result.reason


def test_build_mcp_bwrap_argv_structure(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    argv = build_mcp_bwrap_argv(
        "/usr/bin/bwrap",
        [sys.executable, "-m", "atlas.mcp.memory_server"],
        src_root=src,
        work_dir=work,
    )
    assert "--unshare-all" in argv
    assert "--ro-bind" in argv
    assert "PYTHONPATH=/tmp/atlas_src" in argv
