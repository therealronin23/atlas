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
            install=f"{sys.executable} -m atlas.mcp.memory_server",
        )
    )
    assert result.passed is True
    assert "spawn OK" in result.reason


def test_third_party_local_binary_also_gets_jailed(tmp_path: Path) -> None:
    """Hallazgo 2026-07-23 (al cablear la jaula autónoma): antes de este fix,
    ``_probe_jailed`` solo aislaba módulos ``atlas.mcp.*`` -- un binario LOCAL
    de terceros (no npx/uvx, no atlas-native) caía directo a
    ``probe_mcp_stdio`` SIN jaula, pese a ser precisamente el caso que menos
    confianza merece. El aislamiento bwrap (--unshare-all, sin red, uid
    nobody) no depende de que el comando sea nuestro; debe aplicar a
    cualquier proceso local que se vaya a ejecutar de verdad. Live (bwrap
    real), no mockeado -- ``_probe_jailed`` construye su propio transport
    real y no acepta un ``transport_factory`` inyectado para el camino
    aislado, así que hace falta un binario que exista de verdad."""
    from atlas.security.bwrap_jail import BwrapJail

    if not (FIXTURE.is_file() and BwrapJail.is_available()):
        pytest.skip("requiere bwrap real + fixture")

    src = tmp_path / "src"
    src.mkdir()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    # La jaula solo monta /usr, src_root y work_dir -- ni tests/fixtures/ del
    # repo ni el venv son visibles dentro. Copiar el script al work_dir (que
    # SÍ se bind-monta) y usar el interprete real del sistema.
    script_in_work = work_dir / "echo_server.py"
    script_in_work.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    # El intérprete DEBE vivir bajo /usr para ser visible dentro de la jaula.
    # ``shutil.which("python3")`` puede devolver el del venv
    # (``.venv/bin/python3``), que la jaula NO bind-monta -> rc=127 (test
    # verde/rojo según el PATH). Forzamos el del sistema y saltamos si falta.
    system_python = "/usr/bin/python3"
    if not Path(system_python).is_file():
        pytest.skip("requiere /usr/bin/python3 (intérprete del sistema, visible en la jaula)")
    trial = SpawnTrial(repo_root=tmp_path, work_dir=work_dir, timeout_seconds=10.0)
    # Path directo al fixture (no "-m atlas.mcp.xxx"): is_atlas_native_module
    # es False para esto, es exactamente el caso "de terceros".
    result = trial.probe_cmd([system_python, str(script_in_work)])
    assert result.jailed is True
    assert result.ok is True, result.reason
    assert result.tool_count == 2


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
