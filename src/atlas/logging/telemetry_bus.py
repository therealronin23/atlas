"""
ADR-024 — TelemetryBus: in-process metrics and sampled events (non-forensic).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    labels: dict[str, str]
    value: float
    timestamp: float


Subscriber = Callable[[TelemetryEvent], None]


class TelemetryBus:
    """Thread-safe counters/gauges; does not replace MerkleLogger."""

    def __init__(self, max_events: int = 5000) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._events: list[TelemetryEvent] = []
        self._max_events = max_events
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] += value
            self._emit(name, value, labels)

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._gauges[key] = value
            self._emit(name, value, labels)

    def _emit(self, name: str, value: float, labels: dict[str, str]) -> None:
        ev = TelemetryEvent(name=name, labels=labels, value=value, timestamp=time.time())
        self._events.append(ev)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]
        for sub in self._subscribers:
            try:
                sub(ev)
            except Exception:
                pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {"name": k[0], "labels": dict(k[1]), "value": v}
                for k, v in self._counters.items()
            ]
            gauges = [
                {"name": k[0], "labels": dict(k[1]), "value": v}
                for k, v in self._gauges.items()
            ]
            recent = [
                {
                    "name": e.name,
                    "labels": e.labels,
                    "value": e.value,
                    "timestamp": e.timestamp,
                }
                for e in self._events[-50:]
            ]
        return {"counters": counters, "gauges": gauges, "recent_events": recent}
