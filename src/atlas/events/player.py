"""Event player — reproduce fixtures JSONL como eventos OS SIMULADOS.

Todo evento que pasa por el player queda marcado `simulated=True` salvo que el
fixture ya declare lo contrario explícitamente; jamás fabrica audit.merkle_hash
(OS-R9). Sirve tanto al backend (POST /simulate) como a tests y demos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from atlas.events.schemas import OsEvent
from atlas.events.store import OsEventStore


@dataclass
class ReplayResult:
    """Espejo mínimo de schemas/replay.schema.json."""

    replay_id: str
    source_ref: str
    started_at: str
    status: str = "running"
    finished_at: str | None = None
    event_count: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "replay_id": self.replay_id,
            "source_ref": self.source_ref,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "event_count": self.event_count,
            "errors": list(self.errors),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventPlayer:
    def __init__(self, store: OsEventStore) -> None:
        self._store = store

    def play_fixture(self, fixture_path: Path) -> ReplayResult:
        """Valida cada línea contra el canon y la publica marcada simulated."""
        result = ReplayResult(
            replay_id=f"rpl_{uuid.uuid4().hex[:12]}",
            source_ref=str(fixture_path),
            started_at=_now(),
        )
        try:
            raw_lines = fixture_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            result.status = "failed"
            result.errors.append(str(exc))
            result.finished_at = _now()
            return result

        for lineno, raw in enumerate(raw_lines, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = OsEvent.model_validate_json(raw)
            except ValueError as exc:
                result.errors.append(f"línea {lineno}: {exc}")
                continue
            if event.simulated is None:
                event = event.model_copy(update={"simulated": True})
            if event.audit is not None and event.audit.merkle_hash is not None:
                # Un fixture no puede afirmar auditoría Merkle real (OS-R9).
                result.errors.append(
                    f"línea {lineno}: audit.merkle_hash no permitido en fixtures"
                )
                continue
            self._store.append(event)
            result.event_count += 1

        result.status = "failed" if result.errors and result.event_count == 0 else "completed"
        result.finished_at = _now()
        return result
