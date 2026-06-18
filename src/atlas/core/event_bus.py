"""Atlas Core — Event Bus in-process con eventos tipados."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable

from atlas.core.contracts import Event, EventType

Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass  # Un handler roto no bloquea el bus

    def publish_type(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
        producer: str = "atlas_core",
    ) -> Event:
        evt = Event(
            type=event_type,
            payload=payload or {},
            task_id=task_id,
            producer=producer,
        )
        self.publish(evt)
        return evt
