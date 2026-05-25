"""
Atlas Core — Gate H resilience manager.
H1–H6: receipts, result audit, rebuildable memory, fail-safe, env fingerprints.
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
from atlas.core.environment_sensor import EnvironmentFingerprint, capture_fingerprint
from atlas.core.result_auditor import ResultAuditor, TaskOutput, ValidationResult
from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.memory.memory_system import (
    ApprovedPatternStore,
    ErrorRegistry,
    FailureEntry,
    PatternEntry,
    TruthSnapshotStore,
)

_log = logging.getLogger(__name__)

DEFAULT_KNOWN_GOOD_TOOLS = frozenset({
    "editor.read",
    "fs.list_dir",
    "git.status",
})


@dataclass
class GeneratedToolFailure:
    tool_name: str
    failure_type: str
    error: str
    context: dict[str, Any]
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateHState:
    failure_counts: dict[str, int] = field(default_factory=dict)
    paused_tools: list[str] = field(default_factory=list)
    diagnostic_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_counts": self.failure_counts,
            "paused_tools": self.paused_tools,
            "diagnostic_mode": self.diagnostic_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateHState:
        return cls(
            failure_counts=dict(data.get("failure_counts") or {}),
            paused_tools=list(data.get("paused_tools") or []),
            diagnostic_mode=bool(data.get("diagnostic_mode", False)),
        )


class GateHManager:
    PAUSE_THRESHOLD = 3

    def __init__(
        self,
        workspace: Path,
        merkle: MerkleLogger,
        error_registry: ErrorRegistry,
        approved_patterns: ApprovedPatternStore,
        *,
        vector_store: Any | None = None,
        known_good_tools: frozenset[str] | None = None,
    ) -> None:
        self._workspace = workspace
        self._merkle = merkle
        self._error_registry = error_registry
        self._approved_patterns = approved_patterns
        self._vector_store = vector_store
        self._known_good = known_good_tools or DEFAULT_KNOWN_GOOD_TOOLS
        self._state_path = workspace / "memory" / "gate_h" / "state.json"
        self._snapshot_store = TruthSnapshotStore(
            workspace / "memory" / "truth_snapshots",
            merkle=merkle,
        )
        self._auditor = ResultAuditor(self._snapshot_store, self._approved_patterns)
        self._failure_counts: dict[str, int] = {}
        self._paused_tools: set[str] = set()
        self._diagnostic_mode = False
        self._load_state()

    @property
    def diagnostic_mode(self) -> bool:
        return self._diagnostic_mode

    @property
    def auditor(self) -> ResultAuditor:
        return self._auditor

    @property
    def snapshot_store(self) -> TruthSnapshotStore:
        return self._snapshot_store

    def set_diagnostic_mode(self, enabled: bool) -> None:
        self._diagnostic_mode = enabled
        self._persist_state()
        self._merkle.log(
            action="gate_h.diagnostic_mode",
            agent="gate_h",
            result="on" if enabled else "off",
            risk_level="safe",
            payload={"diagnostic_mode": enabled},
        )

    def is_allowed_in_diagnostic(self, tool_name: str) -> bool:
        if not self._diagnostic_mode:
            return True
        return tool_name in self._known_good

    def record_reasoning_receipt(
        self,
        task_id: str,
        tool_name: str,
        receipt: ReasoningReceipt,
    ) -> AuditRecord:
        return self._merkle.log(
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
        self._persist_state()
        if self.should_pause_tool(tool_name):
            self.pause_tool(tool_name)

    def should_pause_tool(self, tool_name: str) -> bool:
        return self._failure_counts.get(tool_name, 0) >= self.PAUSE_THRESHOLD

    def pause_tool(self, tool_name: str) -> None:
        self._paused_tools.add(tool_name)
        self._persist_state()
        self._merkle.log(
            action="generated_tool.paused",
            agent="gate_h",
            result="success",
            risk_level="critical",
            payload={"tool": tool_name, "failure_count": self._failure_counts.get(tool_name, 0)},
        )

    def resume_tool(self, tool_name: str) -> None:
        self._paused_tools.discard(tool_name)
        self._failure_counts.pop(tool_name, None)
        self._persist_state()
        self._merkle.log(
            action="generated_tool.resumed",
            agent="gate_h",
            result="success",
            risk_level="safe",
            payload={"tool": tool_name},
        )

    def is_tool_paused(self, tool_name: str) -> bool:
        return tool_name in self._paused_tools

    def record_stale_tool(self, tool_name: str, pattern_id: str, task_id: str | None = None) -> None:
        self._merkle.log(
            action="generated_tool.stale",
            agent="gate_h",
            result="blocked",
            risk_level="medium",
            payload={"tool_name": tool_name, "pattern_id": pattern_id},
            task_id=task_id,
        )

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

    def audit_generated_run(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        result: dict[str, Any],
        *,
        task_id: str | None = None,
        promote: bool = True,
    ) -> ValidationResult:
        output = TaskOutput.from_task_result(result)
        snapshot = self._auditor.capture_baseline(
            tool_name,
            input_data,
            output,
            source_task_id=task_id,
        )
        validation = self._auditor.validate_output(snapshot, output)
        if validation.valid and promote:
            entry = self._auditor.promote_if_valid(
                tool_name,
                snapshot,
                output,
                fingerprint=capture_fingerprint(),
            )
            if entry is not None:
                self._merkle.log(
                    action="generated_tool.promoted",
                    agent="gate_h",
                    result="success",
                    risk_level="safe",
                    payload={"pattern_id": entry.id, "tool_name": tool_name},
                    task_id=task_id,
                )
        elif not validation.valid:
            self.record_failure(
                tool_name,
                "validation_failed",
                "; ".join(validation.reasons),
                {"input": input_data, "reasons": list(validation.reasons)},
                task_id=task_id,
            )
        return validation

    def rebuild_memory(self, vector_store: Any | None = None) -> dict[str, int]:
        store = vector_store if vector_store is not None else self._vector_store
        records = self._merkle.read_all()
        restored_patterns = 0
        restored_snapshots = 0
        kuzu_patterns = 0

        self._approved_patterns.clear()
        self._snapshot_store.clear()

        for record in records:
            if record.action == "approved_pattern.added":
                entry_payload = record.payload.get("entry")
                if isinstance(entry_payload, dict):
                    try:
                        pattern = PatternEntry(**entry_payload)
                        self._approved_patterns.add(pattern)
                        restored_patterns += 1
                    except Exception as exc:
                        _log.warning("No se pudo restaurar approved pattern: %s", exc)

            if record.action == "truth_snapshot.recorded":
                snap_payload = record.payload.get("snapshot")
                if isinstance(snap_payload, dict):
                    try:
                        snapshot = TruthSnapshot(**snap_payload)
                        self._snapshot_store.add(snapshot)
                        restored_snapshots += 1
                    except Exception as exc:
                        _log.warning("No se pudo restaurar truth snapshot: %s", exc)

        if store is not None:
            for pattern in self._approved_patterns.all():
                try:
                    store.add_pattern(
                        text=f"{pattern.name}\n{pattern.description}\n{pattern.content}",
                        tags=pattern.tags,
                        pattern_id=pattern.id,
                    )
                    kuzu_patterns += 1
                except Exception as exc:
                    _log.warning("Kuzu add_pattern en rebuild: %s", exc)

        self._merkle.log(
            action="memory.rebuilt",
            agent="gate_h",
            result="success",
            risk_level="safe",
            payload={
                "restored_patterns": restored_patterns,
                "restored_snapshots": restored_snapshots,
                "kuzu_patterns": kuzu_patterns,
            },
        )
        return {
            "restored_patterns": restored_patterns,
            "restored_snapshots": restored_snapshots,
            "kuzu_patterns": kuzu_patterns,
        }

    def status_summary(self) -> dict[str, Any]:
        stale = sum(
            1 for p in self._approved_patterns.all()
            if p.tags and "generated_tool" in p.tags and self._auditor.check_pattern_stale(p)
        )
        return {
            "paused_tools": self.paused_tools,
            "failure_counts": self.failure_counts,
            "truth_snapshots": len(self._snapshot_store.all()),
            "diagnostic_mode": self._diagnostic_mode,
            "stale_patterns_count": stale,
            "known_good_tools": sorted(self._known_good),
        }

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            state = GateHState.from_dict(data)
            self._failure_counts = state.failure_counts
            self._paused_tools = set(state.paused_tools)
            self._diagnostic_mode = state.diagnostic_mode
        except Exception as exc:
            _log.warning("gate_h state load failed: %s", exc)

    def _persist_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = GateHState(
            failure_counts=self._failure_counts,
            paused_tools=sorted(self._paused_tools),
            diagnostic_mode=self._diagnostic_mode,
        )
        self._state_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
