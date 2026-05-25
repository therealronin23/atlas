"""
Gate H1 — Result Auditor: validate generated tool output against TruthSnapshots.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.core.contracts import TruthSnapshot
from atlas.core.environment_sensor import (
    EnvironmentFingerprint,
    capture_fingerprint,
    fingerprint_tag,
    is_stale,
)
from atlas.memory.memory_system import ApprovedPatternStore, PatternEntry, TruthSnapshotStore


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True, reasons=())

    @classmethod
    def fail(cls, *reasons: str) -> ValidationResult:
        return cls(valid=False, reasons=reasons)


@dataclass
class TaskOutput:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    success: bool = True

    @classmethod
    def from_task_result(cls, result: dict[str, Any]) -> TaskOutput:
        return cls(
            exit_code=int(result.get("exit_code", -1)),
            stdout=str(result.get("stdout", "")),
            stderr=str(result.get("stderr", "")),
            success=bool(result.get("success", False)),
        )


class ResultAuditor:
    """Validates tool output shape and promotes patterns when stable."""

    def __init__(
        self,
        snapshot_store: TruthSnapshotStore,
        approved_patterns: ApprovedPatternStore,
    ) -> None:
        self._snapshots = snapshot_store
        self._patterns = approved_patterns

    def build_expected_shape(
        self,
        output: TaskOutput,
        *,
        stdout_contains: str | None = None,
    ) -> dict[str, Any]:
        expected: dict[str, Any] = {"exit_code": output.exit_code, "success": output.success}
        if stdout_contains:
            expected["stdout_contains"] = stdout_contains
        elif output.stdout.strip():
            expected["stdout_contains"] = output.stdout.strip()[:80]
        return expected

    def capture_baseline(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        output: TaskOutput,
        *,
        invariants: dict[str, Any] | None = None,
        source_task_id: str | None = None,
    ) -> TruthSnapshot:
        shape = self.build_expected_shape(
            output,
            stdout_contains=str(input_data.get("expected_stdout_contains", "")) or None,
        )
        if input_data.get("expected_stdout_contains"):
            shape["stdout_contains"] = input_data["expected_stdout_contains"]
        snapshot = TruthSnapshot(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            input_data=input_data,
            expected_output_shape=shape,
            invariants=invariants or {"max_stderr_len": 500},
            source_task_id=source_task_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._snapshots.add(snapshot)
        return snapshot

    def validate_output(self, snapshot: TruthSnapshot, output: TaskOutput) -> ValidationResult:
        shape = snapshot.expected_output_shape
        reasons: list[str] = []

        expected_exit = shape.get("exit_code")
        if expected_exit is not None and output.exit_code != int(expected_exit):
            reasons.append(f"exit_code esperado {expected_exit}, recibido {output.exit_code}")

        if shape.get("success") is True and not output.success:
            reasons.append("success=False en salida")

        contains = shape.get("stdout_contains")
        if contains and str(contains) not in output.stdout:
            reasons.append(f"stdout no contiene '{contains}'")

        max_stderr = int(snapshot.invariants.get("max_stderr_len", 500))
        if len(output.stderr) > max_stderr:
            reasons.append(f"stderr demasiado largo (>{max_stderr})")

        return ValidationResult.ok() if not reasons else ValidationResult.fail(*reasons)

    def shadow_compare(
        self,
        snapshot: TruthSnapshot,
        new_output: TaskOutput,
    ) -> bool:
        return self.validate_output(snapshot, new_output).valid

    def promote_if_valid(
        self,
        tool_name: str,
        snapshot: TruthSnapshot,
        output: TaskOutput,
        *,
        fingerprint: EnvironmentFingerprint | None = None,
    ) -> PatternEntry | None:
        validation = self.validate_output(snapshot, output)
        if not validation.valid:
            return None

        fp = fingerprint or capture_fingerprint()
        tags = ["generated_tool", tool_name, fingerprint_tag(fp)]
        entry = PatternEntry(
            id=f"gen-{snapshot.id[:8]}",
            name=tool_name,
            description=f"Generated tool promoted from snapshot {snapshot.id}",
            pattern_type="generated_script",
            content=str(snapshot.input_data.get("command", "")),
            tags=tags,
        )
        self._patterns.add(entry)
        return entry

    def check_pattern_stale(self, pattern: PatternEntry) -> bool:
        from atlas.core.environment_sensor import fingerprint_from_tags

        stored = fingerprint_from_tags(pattern.tags)
        if stored is None:
            return False
        return is_stale(stored)
