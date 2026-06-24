"""
ADR-024 — Operational WAL: high-volume debug trace with rotation (no secrets).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class OperationalWAL:
    """Rotating JSONL trace for debugging; redacts obvious secret keys."""

    MAX_BYTES = 5 * 1024 * 1024
    REDACT_KEYS = frozenset({
        "api_key", "token", "secret", "password", "passphrase", "authorization",
    })

    def __init__(self, log_dir: Path) -> None:
        self._dir = log_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "operational.jsonl"
        self._lock = threading.Lock()

    def write(self, component: str, message: str, **fields: Any) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "component": component,
            "message": message,
            "fields": self._redact(fields),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            self._rotate_if_needed(len(line) + 1)
            with self._file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _redact(self, fields: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in fields.items():
            if any(r in k.lower() for r in self.REDACT_KEYS):
                out[k] = "[REDACTED]"
            else:
                out[k] = v
        return out

    def _rotate_if_needed(self, incoming: int) -> None:
        if not self._file.exists():
            return
        if self._file.stat().st_size + incoming <= self.MAX_BYTES:
            return
        ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        rotated = self._dir / f"operational.{ts}.jsonl"
        # Avoid silent overwrite when two rotations happen within the same second:
        # append a collision counter until we find an unused path.
        counter = 1
        while rotated.exists():
            rotated = self._dir / f"operational.{ts}-{counter}.jsonl"
            counter += 1
        self._file.replace(rotated)

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        lines = self._file.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
