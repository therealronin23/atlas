"""
Tests para Gate H: resiliencia auditada y reconstruccion de memoria.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.contracts import ReasoningReceipt
from atlas.core.orchestrator import Orchestrator
from atlas.memory.memory_system import PatternEntry


def test_gate_h_rebuild_memory_restores_approved_patterns(tmp_path: Path) -> None:
    workspace = tmp_path / "atlas"
    workspace.mkdir()
    orch = Orchestrator(workspace=workspace)

    pattern = PatternEntry(
        id="pattern-1",
        name="test pattern",
        description="Test approved pattern",
        pattern_type="workflow",
        content="print('ok')",
    )
    orch._approved_patterns.add(pattern)
    assert len(orch._approved_patterns.all()) == 1

    orch._approved_patterns.clear()
    assert len(orch._approved_patterns.all()) == 0

    result = orch.rebuild_memory()
    assert result["restored_patterns"] == 1
    assert result["restored_snapshots"] >= 0
    restored = orch._approved_patterns.all()
    assert len(restored) == 1
    assert restored[0].id == "pattern-1"
    assert restored[0].name == "test pattern"


def test_gate_h_failure_pause_after_repeated_failures(tmp_path: Path) -> None:
    workspace = tmp_path / "atlas"
    workspace.mkdir()
    orch = Orchestrator(workspace=workspace)

    for attempt in range(3):
        orch._gate_h.record_failure(
            tool_name="generated_tool.test",
            failure_type="runtime_error",
            error=f"error attempt {attempt}",
            context={"attempt": attempt},
            task_id=None,
        )

    status = orch.gate_h_status()
    assert status["failure_counts"].get("generated_tool.test") == 3
    assert "generated_tool.test" in status["paused_tools"]


def test_gate_h_record_reasoning_receipt_logs_success(tmp_path: Path) -> None:
    workspace = tmp_path / "atlas"
    workspace.mkdir()
    orch = Orchestrator(workspace=workspace)

    receipt = ReasoningReceipt(
        purpose="Validate generated tool execution",
        data_touched=["workspace/config/governance.json"],
        permissions_required=["confirm"],
        safety_checks=["AST Guard", "MerkleLogger"],
        approval_path="automatic",
    )

    record = orch._gate_h.record_reasoning_receipt(
        task_id="task-123",
        tool_name="generated_tool.validate",
        receipt=receipt,
    )

    assert record.action == "generated_tool.receipt"
    assert record.payload["tool_name"] == "generated_tool.validate"
    assert record.payload["receipt"]["purpose"] == "Validate generated tool execution"
