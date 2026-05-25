"""
Atlas Core — Gate H resilience manager.
Controla recibos estructurados, fallas de herramientas generadas y reconstruccion de memoria.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.contracts import ReasoningReceipt, TruthSnapshot
from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.memory.memory_system import ApprovedPatternStore, ErrorRegistry, FailureEntry, TruthSnapshotStore

_log = logging.getLogger(__name__)


@dataclass
class GeneratedToolFailure:
    tool_name: str
    failure_type: str
    error: str
    context: dict[str, Any]
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class GateHManager:
    PAUSE_THRESHOLD = 3

    def __init__(
        self,
        workspace: Path,
        merkle: MerkleLogger,
        error_registry: ErrorRegistry,
        approved_patterns: ApprovedPatternStore,
    ) -> None:
        self._workspace = workspace
        self._merkle = merkle
        self._error_registry = error_registry
        self._approved_patterns = approved_patterns
        self._failure_counts: dict[str, int] = {}
        self._paused_tools: set[str] = set()
        self._snapshot_store = TruthSnapshotStore(
            workspace / "memory" / "truth_snapshots",
            merkle=merkle,
        )

    def record_reasoning_receipt(
        self,
        task_id: str,
        tool_name: str,
        receipt: ReasoningReceipt,
    ) -> AuditRecord:
        record = self._merkle.log(
            action="generated_tool.receipt",
            agent="gate_h",
            result="success",
            risk_level="medium",
            payload={
                "task_id": task_id,
                "tool_name": tool_name,
                "receipt": receipt.to_dict(),
            },
            task_id=task_id,
        )
        return record

    def record_failure(
        self,
        tool_name: str,
        failure_type: str,
        error: str,
        context: dict[str, Any],
        task_id: str | None = None,
    ) -> None:
        self._failure_counts[tool_name] = self._failure_counts.get(tool_name, 0) + 1
        failure = GeneratedToolFailure(
            tool_name=tool_name,
            failure_type=failure_type,
            error=error,
            context=context,
        )
        self._merkle.log(
            action="tool.failed",
            agent="gate_h",
            result="failure",
            risk_level="high",
            payload={"failure": failure.to_dict(), "paused": self.is_tool_paused(tool_name)},
            task_id=task_id,
        )
        self._error_registry.record(
            FailureEntry(
                id=str(uuid.uuid4()),
                error_type=failure_type,
                description=error,
                context={"tool_name": tool_name, **context},
                solution="Revisar y estabilizar el flujo de herramienta generada.",
                tags=["gate_h", tool_name],
            )
        )
        if self.should_pause_tool(tool_name):
            self.pause_tool(tool_name)

    def should_pause_tool(self, tool_name: str) -> bool:
        return self._failure_counts.get(tool_name, 0) >= self.PAUSE_THRESHOLD

    def pause_tool(self, tool_name: str) -> None:
        self._paused_tools.add(tool_name)
        self._merkle.log(
            action="generated_tool.paused",
            agent="gate_h",
            result="success",
            risk_level="critical",
            payload={"tool": tool_name, "failure_count": self._failure_counts.get(tool_name, 0)},
        )

    def is_tool_paused(self, tool_name: str) -> bool:
        return tool_name in self._paused_tools

    @property
    def failure_counts(self) -> dict[str, int]:
        return dict(self._failure_counts)

    @property
    def paused_tools(self) -> list[str]:
        return sorted(self._paused_tools)

    def create_truth_snapshot(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        expected_output_shape: dict[str, Any],
        invariants: dict[str, Any] | None = None,
        source_task_id: str | None = None,
    ) -> TruthSnapshot:
        snapshot = TruthSnapshot(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            input_data=input_data,
            expected_output_shape=expected_output_shape,
            invariants=invariants or {},
            source_task_id=source_task_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._snapshot_store.add(snapshot)
        return snapshot

    def rebuild_memory(self) -> dict[str, int]:
        records = self._merkle.read_all()
        restored_patterns = 0
        restored_snapshots = 0
        self._approved_patterns.clear()
        self._snapshot_store.clear()

        for record in records:
            if record.action == "approved_pattern.added":
                entry_payload = record.payload.get("entry")
                if isinstance(entry_payload, dict):
                    try:
                        from atlas.memory.memory_system import PatternEntry
                        pattern = PatternEntry(**entry_payload)
                        self._approved_patterns.add(pattern)
                        restored_patterns += 1
                    except Exception as exc:
                        _log.warning("No se pudo restaurar approved pattern: %s", exc)
            if record.action == "generated_tool.receipt":
                snapshot_payload = record.payload.get("receipt", {})
                if isinstance(snapshot_payload, dict):
                    created_at = snapshot_payload.get("created_at")
                    try:
                        snapshot = TruthSnapshot(
                            id=str(uuid.uuid4()),
                            tool_name=snapshot_payload.get("purpose", "unknown"),
                            input_data={"meta": snapshot_payload},
                            expected_output_shape={},
                            invariants={}
                        )
                        self._snapshot_store.add(snapshot)
                        restored_snapshots += 1
                    except Exception as exc:
                        _log.warning("No se pudo restaurar truth snapshot: %s", exc)

        self._merkle.log(
            action="memory.rebuilt",
            agent="gate_h",
            result="success",
            risk_level="safe",
            payload={"restored_patterns": restored_patterns, "restored_snapshots": restored_snapshots},
        )
        return {
            "restored_patterns": restored_patterns,
            "restored_snapshots": restored_snapshots,
        }
