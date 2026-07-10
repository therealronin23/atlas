"""Event store OS — JSONL append-only con suscriptores y replay (ADR-058).

Autoridad de REPRESENTACIÓN, no de auditoría: la auditoría sigue siendo el
Merkle de transparency/. El store vive fuera del árbol git, en
`$ATLAS_HOME/os_events/events.jsonl` (misma convención que core/reality.py).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from atlas.events.schemas import OsEvent

Listener = Callable[[OsEvent], None]


def default_store_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "os_events" / "events.jsonl"


class OsEventStore:
    """Append-only JSONL + notificación in-process a suscriptores (WS, UI)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_store_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    @property
    def path(self) -> Path:
        return self._path

    def subscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def append(self, event: OsEvent) -> OsEvent:
        line = event.model_dump_json(exclude_none=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # noqa: BLE001 — un listener roto no bloquea el store
                pass
        return event

    def iter_events(self) -> Iterator[OsEvent]:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    yield OsEvent.model_validate_json(raw)

    def read(self, limit: int | None = None, offset: int = 0) -> list[OsEvent]:
        events = list(self.iter_events())[offset:]
        return events if limit is None else events[:limit]

    def tail(self, n: int) -> list[OsEvent]:
        events = list(self.iter_events())
        return events[-n:]

    def count(self) -> int:
        return sum(1 for _ in self.iter_events())
