"""
ADR-024 — ObservabilityStack facade wired to MerkleLogger.
"""

from __future__ import annotations

from pathlib import Path

from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.logging.microledger import MicroLedger
from atlas.logging.operational_wal import OperationalWAL
from atlas.logging.telemetry_bus import TelemetryBus


class ObservabilityStack:
    """Telemetry + MicroLedger + WAL; Merkle remains authoritative."""

    def __init__(self, workspace: Path) -> None:
        obs_dir = workspace / "memory" / "observability"
        self.telemetry = TelemetryBus()
        self.microledger = MicroLedger(obs_dir / "microledger.jsonl")
        self.wal = OperationalWAL(obs_dir / "wal")
        self._telemetry_by_action = {
            "task.completed": ("atlas_tasks_total", {"status": "done"}),
            "task.failed": ("atlas_tasks_total", {"status": "failed"}),
            "model.called": ("atlas_model_calls_total", {}),
            "thermal.alert": ("atlas_thermal_alerts_total", {}),
        }

    def on_merkle_record(self, record: AuditRecord) -> None:
        self.microledger.ingest_merkle_record(record)
        self.wal.write(
            record.agent,
            record.action,
            result=record.result,
            risk=record.risk_level,
            task_id=record.task_id,
        )
        spec = self._telemetry_by_action.get(record.action)
        if spec:
            name, labels = spec
            self.telemetry.inc(name, 1.0, **labels, result=record.result)

    def wrap_merkle(self, merkle: MerkleLogger) -> MerkleLogger:
        """Return MerkleLogger that notifies this stack on each append."""
        stack = self
        original_append = merkle.append

        def append_with_obs(record: AuditRecord) -> AuditRecord:
            linked = original_append(record)
            stack.on_merkle_record(linked)
            return linked

        merkle.append = append_with_obs  # type: ignore[method-assign]
        return merkle

    def snapshot(self) -> dict:
        return {
            "telemetry": self.telemetry.snapshot(),
            "microledger_tail": self.microledger.tail(20),
            "wal_tail": self.wal.tail(10),
        }
