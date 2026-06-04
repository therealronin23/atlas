"""ADR-039 slice 1 — Scout read-only de salud/deuda.

El Scout solo observa: deriva señales deterministas de los providers read-only
inyectados y audita el informe en Merkle. No muta nada, no propone nada. Los
providers se mockean (sin subprocess ni inferencia real)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.self_maintenance import (
    SEVERITY_ALERT,
    SEVERITY_INFO,
    SEVERITY_WARN,
    MaintenanceScout,
    ScoutReport,
)
from atlas.logging.merkle_logger import MerkleLogger


def _healthy() -> dict:
    return {
        "merkle_chain_ok": True,
        "emergency_mode": False,
        "governance_ok": True,
        "thermal_mode": "normal",
        "hermes_reachable": True,
        "queue_depth": 0,
        "pending_approvals_count": 0,
    }


def _clean_git() -> dict:
    return {"stdout": "", "stderr": "", "returncode": 0, "repo_root": "/repo"}


def _make_scout(
    merkle: MerkleLogger,
    *,
    health: dict | None = None,
    git: dict | None = None,
    failures: list | None = None,
    threshold: int = 3,
) -> MaintenanceScout:
    return MaintenanceScout(
        merkle=merkle,
        health_provider=lambda: health if health is not None else _healthy(),
        git_status_provider=lambda: git if git is not None else _clean_git(),
        failure_provider=lambda: failures if failures is not None else [],
        recent_failure_threshold=threshold,
    )


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _kinds(report: ScoutReport) -> set[str]:
    return {s.kind for s in report.signals}


class TestScoutObservation:
    def test_healthy_system_has_no_warnings(self, merkle) -> None:
        report = _make_scout(merkle).survey()
        assert isinstance(report, ScoutReport)
        assert report.signals == []
        assert report.max_severity == SEVERITY_INFO
        assert report.recent_failures == 0

    def test_broken_merkle_chain_is_alert(self, merkle) -> None:
        health = _healthy() | {"merkle_chain_ok": False}
        report = _make_scout(merkle, health=health).survey()
        assert "merkle_chain_broken" in _kinds(report)
        assert report.max_severity == SEVERITY_ALERT

    def test_emergency_mode_is_alert(self, merkle) -> None:
        health = _healthy() | {"emergency_mode": True}
        report = _make_scout(merkle, health=health).survey()
        assert "emergency_mode" in _kinds(report)
        assert report.max_severity == SEVERITY_ALERT

    def test_thermal_throttle_is_warn(self, merkle) -> None:
        health = _healthy() | {"thermal_mode": "omega"}
        report = _make_scout(merkle, health=health).survey()
        sig = next(s for s in report.signals if s.kind == "thermal_throttled")
        assert sig.severity == SEVERITY_WARN
        assert sig.value == "omega"

    def test_hermes_unreachable_is_warn(self, merkle) -> None:
        health = _healthy() | {"hermes_reachable": False, "hermes_mode": "mock"}
        report = _make_scout(merkle, health=health).survey()
        assert "hermes_unreachable" in _kinds(report)
        assert report.max_severity == SEVERITY_WARN

    def test_failure_backlog_over_threshold_is_warn(self, merkle) -> None:
        report = _make_scout(merkle, failures=[1, 2, 3, 4], threshold=3).survey()
        sig = next(s for s in report.signals if s.kind == "failure_backlog")
        assert sig.severity == SEVERITY_WARN
        assert sig.value == 4
        assert report.recent_failures == 4

    def test_failures_under_threshold_silent(self, merkle) -> None:
        report = _make_scout(merkle, failures=[1, 2], threshold=3).survey()
        assert "failure_backlog" not in _kinds(report)

    def test_offline_and_pending_are_info(self, merkle) -> None:
        health = _healthy() | {"queue_depth": 5, "pending_approvals_count": 2}
        report = _make_scout(merkle, health=health).survey()
        kinds = _kinds(report)
        assert "offline_backlog" in kinds and "pending_approvals" in kinds
        assert report.max_severity == SEVERITY_INFO

    def test_dirty_workspace_is_info(self, merkle) -> None:
        git = {"stdout": " M a.py\n?? b.py\n", "returncode": 0}
        report = _make_scout(merkle, git=git).survey()
        sig = next(s for s in report.signals if s.kind == "workspace_dirty")
        assert sig.severity == SEVERITY_INFO
        assert sig.value == 2

    def test_git_error_is_warn(self, merkle) -> None:
        report = _make_scout(merkle, git={"error": "capability denegada"}).survey()
        assert "git_unavailable" in _kinds(report)
        assert report.max_severity == SEVERITY_WARN

    def test_alert_dominates_aggregate_severity(self, merkle) -> None:
        health = _healthy() | {
            "merkle_chain_ok": False,
            "queue_depth": 3,
            "thermal_mode": "degraded",
        }
        report = _make_scout(merkle, health=health).survey()
        assert report.max_severity == SEVERITY_ALERT


class TestScoutAudit:
    def test_survey_is_logged_in_merkle(self, merkle) -> None:
        health = _healthy() | {"merkle_chain_ok": False}
        report = _make_scout(merkle, health=health).survey()
        records = [r.to_dict() for r in merkle.tail(20)]
        surveys = [r for r in records if r["action"] == "self_maintenance.scout_survey"]
        assert surveys, "el survey no se auditó en Merkle"
        payload = surveys[-1]["payload"]
        assert payload["report_id"] == report.id
        assert payload["max_severity"] == SEVERITY_ALERT
        assert "merkle_chain_broken" in payload["signal_kinds"]

    def test_audit_failure_does_not_break_survey(self, merkle, monkeypatch) -> None:
        def _boom(*a, **k):
            raise RuntimeError("merkle caído")

        monkeypatch.setattr(merkle, "log", _boom)
        # No debe propagar: la auditoría no rompe la observación.
        report = _make_scout(merkle).survey()
        assert isinstance(report, ScoutReport)

    def test_to_dict_roundtrip_shape(self, merkle) -> None:
        report = _make_scout(merkle, failures=[1, 2, 3], threshold=3).survey()
        d = report.to_dict()
        assert set(d) == {
            "id", "generated_at", "health", "git",
            "recent_failures", "max_severity", "signals",
        }
        assert isinstance(d["signals"], list)
        assert all("kind" in s and "severity" in s for s in d["signals"])


class TestScoutWiring:
    def test_orchestrator_exposes_scout(self, tmp_path: Path) -> None:
        from atlas.core.orchestrator import Orchestrator
        import atlas.governance.governance_l0 as g

        g.GovernanceL0._instance = None
        ws = tmp_path / "atlas"
        ws.mkdir()
        try:
            orch = Orchestrator(workspace=ws)
            scout = orch.maintenance_scout()
            assert orch.maintenance_scout() is scout  # lazy singleton
            report = scout.survey()
            assert isinstance(report, ScoutReport)
            # Cableado a primitivas reales: health_report siempre trae versión.
            assert "version" in report.health
        finally:
            g.GovernanceL0._instance = None
