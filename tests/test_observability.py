"""ADR-024 observability stack tests."""

from __future__ import annotations

from pathlib import Path

from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.logging.observability import ObservabilityStack


def test_observability_ingests_merkle_record(tmp_path: Path) -> None:
    stack = ObservabilityStack(tmp_path / "atlas")
    merkle = stack.wrap_merkle(MerkleLogger(tmp_path / "atlas" / "memory" / "audit"))
    merkle.log(
        action="task.completed",
        agent="test",
        result="success",
        risk_level="safe",
        payload={"tool": "echo"},
    )
    snap = stack.snapshot()
    assert snap["telemetry"]["counters"]
    assert any(
        c["name"] == "atlas_tasks_total" for c in snap["telemetry"]["counters"]
    )
    assert len(stack.microledger.tail(5)) >= 1


def test_operational_wal_redacts_secrets(tmp_path: Path) -> None:
    stack = ObservabilityStack(tmp_path / "atlas")
    stack.wal.write("test", "evt", api_key="secret-value")
    tail = stack.wal.tail(1)
    assert tail[0]["fields"]["api_key"] == "[REDACTED]"
