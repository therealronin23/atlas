"""Gate H extended tests — H3/H4 persistence and diagnostic."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    return Orchestrator(workspace=tmp_path / "atlas")


def test_pause_state_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "atlas"
    monkeypatch.setenv("ATLAS_HOME", str(ws))
    o1 = Orchestrator(workspace=ws)
    o1._gate_h.pause_tool("generated_tool.test")
    o2 = Orchestrator(workspace=ws)
    assert o2._gate_h.is_tool_paused("generated_tool.test")


def test_diagnostic_blocks_unknown_tool(orch: Orchestrator) -> None:
    orch._gate_h.set_diagnostic_mode(True)
    block = orch._check_gate_h_tool_allowed("browser.navigate")
    assert block is not None
    assert "diagnostico" in block.lower()


def test_rebuild_restores_truth_snapshot(orch: Orchestrator) -> None:
    snap = orch._gate_h.create_truth_snapshot(
        "tool.x",
        {"cmd": "echo"},
        {"exit_code": 0},
    )
    orch._gate_h._snapshot_store.clear()
    assert len(orch._gate_h._snapshot_store.all()) == 0
    result = orch.rebuild_memory()
    assert result["restored_snapshots"] >= 1
    ids = {s.id for s in orch._gate_h._snapshot_store.all()}
    assert snap.id in ids


def test_assert_generated_reusable_blocks_stale_pattern(orch: Orchestrator) -> None:
    from atlas.core.environment_sensor import EnvironmentFingerprint, fingerprint_tag
    from atlas.memory.memory_system import PatternEntry

    stored = EnvironmentFingerprint(
        python_version="0.0.0",
        atlas_version="0.0.0",
        dependency_hash="stale-test",
    )
    entry = PatternEntry(
        id="gen-stale-1",
        name="editor.run",
        description="stale",
        pattern_type="generated_script",
        content="echo stale-block",
        tags=["generated_tool", "editor.run", fingerprint_tag(stored)],
    )
    orch._approved_patterns.add(entry)
    with pytest.raises(RuntimeError, match="stale"):
        orch._gate_h.assert_generated_reusable("echo stale-block")


def test_gate_f_success_emits_receipt(orch: Orchestrator) -> None:
    target = Path(orch.status().workspace) / "projects" / "r.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")
    task = orch.handle_intent("editor read projects/r.txt")
    assert task.status.value == "done"
    receipts = orch.gate_h_receipts(5)
    assert any(r.get("payload", {}).get("tool_name") == "editor.read" for r in receipts)
