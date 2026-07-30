"""Tests de `maintenance_workbench_compliance_review_tick` (2026-07-30,
ítem de backlog t4-workbench-compliance-review-tick).

t4-workbench-mandatory-hook deja hallazgos durables (JSONL,
workspace/mcp/workbench_compliance_findings.jsonl) cuando una sesión arranca
sin consultar workbench://manifest, pero nada LEÍA ese fichero -- mismo
patrón "wire-before-claim" que el resto de la auditoría 2026-07-23. Espejo
exacto de maintenance_provider_status_tick: opt-in por env
(ATLAS_WORKBENCH_COMPLIANCE_REVIEW=1), guardia anti-recursión, cadencia 24h,
Merkle. Nunca borra ni muta el fichero de hallazgos.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _write_findings(root: Path, n: int, *, hours_ago: float = 1.0) -> None:
    path = root / "workspace" / "mcp" / "workbench_compliance_findings.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    lines = [
        json.dumps({"at": at.isoformat(), "prompt_hash": "x" * 10, "finding": "workbench_not_consulted"})
        for _ in range(n)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestWorkbenchComplianceReviewTickDisabledAndGuard:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_workbench_compliance_review_tick() == {"status": "disabled"}

    def test_nested_run_guard_beats_missing_env_and_enabled_env(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        assert orch.maintenance_workbench_compliance_review_tick() == {"status": "nested_run_guard"}

        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        assert orch.maintenance_workbench_compliance_review_tick() == {"status": "nested_run_guard"}


class TestWorkbenchComplianceReviewTickFirstRun:
    def test_first_run_writes_state_with_verdict(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        root = Path(str(orch._project_root()))
        _write_findings(root, 5)

        result = orch.maintenance_workbench_compliance_review_tick()

        assert result["status"] == "ran"
        assert result["verdict"] == "normal"
        assert result["total"] == 5

        state_path = root / "workspace" / "self_build" / "workbench_compliance_review_state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "last_run_date" in state
        assert state["last_result"]["verdict"] == "normal"

    def test_first_run_reports_elevated_verdict(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        root = Path(str(orch._project_root()))
        _write_findings(root, 25)

        result = orch.maintenance_workbench_compliance_review_tick()

        assert result["status"] == "ran"
        assert result["verdict"] == "elevated"

    def test_first_run_without_findings_file_is_honest(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")

        result = orch.maintenance_workbench_compliance_review_tick()

        assert result["status"] == "ran"
        assert result["verdict"] == "no_findings"

    def test_never_deletes_or_mutates_findings_file(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        root = Path(str(orch._project_root()))
        _write_findings(root, 3)
        findings_path = root / "workspace" / "mcp" / "workbench_compliance_findings.jsonl"
        before = findings_path.read_text(encoding="utf-8")

        orch.maintenance_workbench_compliance_review_tick()

        assert findings_path.read_text(encoding="utf-8") == before


class TestWorkbenchComplianceReviewTickCadence:
    def test_second_call_same_day_is_a_noop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        root = Path(str(orch._project_root()))
        _write_findings(root, 3)

        first = orch.maintenance_workbench_compliance_review_tick()
        second = orch.maintenance_workbench_compliance_review_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}


class TestWorkbenchComplianceReviewTickMerkle:
    def test_merkle_action_logged_with_verdict(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_WORKBENCH_COMPLIANCE_REVIEW", "1")
        root = Path(str(orch._project_root()))
        _write_findings(root, 25)

        orch.maintenance_workbench_compliance_review_tick()

        records = [
            r for r in orch._merkle.read_all()
            if r.action == "self_maintenance.workbench_compliance_review_tick"
        ]
        assert len(records) == 1
        record = records[0]
        assert record.result == "ran"
        assert record.payload["verdict"] == "elevated"


class TestWorkbenchComplianceReviewTickIsolatedCycle:
    def test_registered_alongside_provider_status_cycle_in_scheduler(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scheduler = orch.maintenance_scheduler()
        assert len(scheduler._extra_cycles) >= 10
