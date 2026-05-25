"""
ADR-024 — MicroLedger: compact rolling summaries derived from Merkle audit records.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import AuditRecord


@dataclass
class MicroLedgerEntry:
    merkle_id: str
    action: str
    agent: str
    result: str
    risk_level: str
    summary: str
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MicroLedger:
    """Append-only compact ledger; summaries only, no raw PII payloads."""

    MAX_ENTRIES = 2000
    SUMMARY_ACTIONS = frozenset({
        "task.completed", "task.failed", "task.blocked",
        "model.called", "model.timeout", "thermal.alert",
        "generated_tool.promoted", "generated_tool.stale",
        "service.started", "service.stopped", "cold_update.proposed",
        "cold_update.validated", "cold_update.applied",
    })

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def ingest_merkle_record(self, record: AuditRecord) -> MicroLedgerEntry | None:
        if record.action not in self.SUMMARY_ACTIONS:
            return None
        summary = self._summarize(record)
        entry = MicroLedgerEntry(
            merkle_id=record.id,
            action=record.action,
            agent=record.agent,
            result=record.result,
            risk_level=record.risk_level,
            summary=summary,
        )
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            self._trim_if_needed()
        return entry

    @staticmethod
    def _summarize(record: AuditRecord) -> str:
        payload = record.payload or {}
        safe_keys = ("tool", "provider", "tool_name", "version", "pattern_id", "proposal_id")
        parts = [f"{k}={payload[k]}" for k in safe_keys if k in payload]
        if record.task_id:
            parts.append(f"task={record.task_id[:8]}")
        return "; ".join(parts) if parts else record.action

    def _trim_if_needed(self) -> None:
        if not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self.MAX_ENTRIES:
            return
        keep = lines[-self.MAX_ENTRIES :]
        self._path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def tail(self, n: int = 30) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
