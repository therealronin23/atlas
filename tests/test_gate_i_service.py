"""Gate I — service runner and health report."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.runtime.service_runner import AtlasServiceRunner


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    # ATLAS_CORE_ROOT: sin esto, cualquier extra_cycle real del scheduler
    # (self-build/research/provider-smoke) que se dispare en un test opera
    # sobre el REPO REAL, no tmp_path (incidente 2026-07-09: 13 worktrees
    # git reales + cascada de subprocess pytest — ver test_maintenance_autoloop.py).
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    return Orchestrator(workspace=tmp_path / "atlas")


def test_health_report_fields(orch: Orchestrator) -> None:
    h = orch.health_report()
    assert h["version"] == orch.VERSION
    assert "governance_ok" in h
    assert "merkle_chain_ok" in h
    assert "gate_h" in h
    assert "pending_approvals_count" in h


def test_service_runner_start_stop(orch: Orchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Disable Prometheus/dashboard/thermal so they don't try to bind real ports
    monkeypatch.delenv("ATLAS_PROMETHEUS", raising=False)
    monkeypatch.delenv("ATLAS_SERVE_DASHBOARD", raising=False)
    monkeypatch.delenv("ATLAS_THERMAL_MONITOR", raising=False)
    runner = AtlasServiceRunner(orch)
    runner.start()
    assert runner._running
    assert orch._offline_monitor is not None
    runner.stop()
    assert not runner._running
