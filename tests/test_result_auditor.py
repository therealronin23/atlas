"""Gate H1 — ResultAuditor tests."""

from __future__ import annotations

from pathlib import Path

from atlas.core.result_auditor import ResultAuditor, TaskOutput
from atlas.core.gate_h import GateHManager
from atlas.core.orchestrator import Orchestrator
from atlas.memory.memory_system import TruthSnapshotStore, ApprovedPatternStore


def test_validate_output_and_promote(tmp_path: Path) -> None:
    store_path = tmp_path / "snapshots"
    patterns_path = tmp_path / "patterns"
    auditor = ResultAuditor(
        TruthSnapshotStore(store_path),
        ApprovedPatternStore(patterns_path),
    )
    output = TaskOutput(exit_code=0, stdout="hello gate h", success=True)
    snapshot = auditor.capture_baseline(
        "editor.run",
        {"command": "echo hello gate h", "working_dir": "tmp"},
        output,
    )
    assert auditor.validate_output(snapshot, output).valid
    entry = auditor.promote_if_valid("editor.run", snapshot, output)
    assert entry is not None
    assert "generated_tool" in entry.tags


def test_shadow_compare_detects_regression(tmp_path: Path) -> None:
    auditor = ResultAuditor(
        TruthSnapshotStore(tmp_path / "s"),
        ApprovedPatternStore(tmp_path / "p"),
    )
    snap = auditor.capture_baseline(
        "t",
        {"command": "echo ok"},
        TaskOutput(exit_code=0, stdout="ok", success=True),
    )
    assert auditor.shadow_compare(snap, TaskOutput(exit_code=0, stdout="ok", success=True))
    assert not auditor.shadow_compare(
        snap, TaskOutput(exit_code=1, stdout="fail", success=False),
    )


def test_generated_run_audit_integration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    orch = Orchestrator(workspace=tmp_path / "atlas")
    gen_dir = tmp_path / "atlas" / "projects" / ".atlas" / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    task = orch.handle_intent("editor run projects/.atlas/generated :: echo gate h ok")
    assert task.status.value == "awaiting_approval"
    orch.approve_pending(task.id, approved=True)
    assert task.status.value == "done"
    assert task.result.get("gate_h", {}).get("valid") is True
