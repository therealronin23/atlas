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
    runner = AtlasServiceRunner(orch)
    runner.start()
    assert runner._running
    assert orch._offline_monitor is not None
    runner.stop()
    assert not runner._running
