"""maintenance_sentinel_revet_tick — Capa 6 de SentinelGate cableada al ciclo
real (2026-07-24, t4-sentinel-scheduled-revet).

Re-minado de claude-mcp-sentinel v3.1: "scheduled monitoring, corre cada
mañana, re-escanea todo". Cierra el mismo patrón wire-before-claim que
mcp_trial_tick: la Capa 6 estaba solo diseñada en ADR-038, sin ningún tick
real que la corriera.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mcp_echo_server.py"


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_SENTINEL_REVET", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    workspace = tmp_path / "atlas"
    workspace.mkdir(parents=True)
    (workspace / "mcp_servers.json").write_text(
        json.dumps([{
            "name": "echo",
            "cmd": [sys.executable, str(FIXTURE)],
            "read_only_tools": ["echo"],
            "enabled": True,
        }]),
        encoding="utf-8",
    )
    return Orchestrator(workspace=workspace)


def test_disabled_without_env_flag(orch: Orchestrator) -> None:
    assert orch.maintenance_sentinel_revet_tick() == {"status": "disabled"}


def test_nested_run_guard_beats_enable_flag(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_SENTINEL_REVET", "1")
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    assert orch.maintenance_sentinel_revet_tick() == {"status": "nested_run_guard"}


def test_revet_tick_reports_no_findings_for_clean_servers(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_SENTINEL_REVET", "1")
    orch.start_mcp_servers()
    try:
        result = orch.maintenance_sentinel_revet_tick()
        assert result == {"status": "ran", "findings": []}
    finally:
        orch._mcp.close_all()


def test_revet_tick_detects_drift_and_never_rewrites_snapshot(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_SENTINEL_REVET", "1")
    orch.start_mcp_servers()
    try:
        snap_path = orch._workspace / "memory" / "sentinel" / "echo.json"
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        snap["echo"] = "0" * 64
        snap_path.write_text(json.dumps(snap), encoding="utf-8")

        result = orch.maintenance_sentinel_revet_tick()

        assert result["status"] == "ran"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["server"] == "echo"
        assert result["findings"][0]["revoked"] is True
        assert orch._mcp.ensure_started("echo") is False

        # nunca re-arma TOFU: el snapshot manipulado sigue igual
        assert json.loads(snap_path.read_text(encoding="utf-8"))["echo"] == "0" * 64
    finally:
        orch._mcp.close_all()
