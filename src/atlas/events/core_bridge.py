"""Bridge suscriptor: proyecta contracts.Event (bus real) → OsEvent (canon OS).

ADR-058: el canon OS es una PROYECCIÓN del EventBus existente, nunca un
segundo bus. Este módulo es el único punto donde se mapean EventType del core
a eventos OS — si el mapping crece, crece aquí y en su test.

No toca core/contracts.py ni core/event_bus.py: solo se suscribe.
"""

from __future__ import annotations

import uuid

from atlas.core.contracts import Event, EventType
from atlas.core.event_bus import EventBus
from atlas.events.schemas import EventStatus, OsEvent, Risk
from atlas.events.store import OsEventStore

# Riesgo representacional por tipo de evento del core. Default: low.
_RISK_BY_TYPE: dict[EventType, Risk] = {
    EventType.SECURITY_VIOLATION: Risk.HIGH,
}


def project_core_event(event: Event) -> OsEvent:
    """Mapping único core→OS. simulated=False: esto SÍ pasó en el runtime."""
    return OsEvent(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        type=event.type.value,
        timestamp=event.timestamp,
        source=f"atlas.core.{event.producer}",
        process_id=event.task_id,
        actor=event.producer,
        summary=f"{event.type.value}"
        + (f" (task {event.task_id})" if event.task_id else ""),
        status=EventStatus.COMPLETED,
        risk=_RISK_BY_TYPE.get(event.type, Risk.LOW),
        visible=True,
        simulated=False,
        payload=dict(event.payload),
        audit=None,  # el hash Merkle solo lo aporta transparency/, no este bridge
    )


class CoreEventBridge:
    def __init__(self, bus: EventBus, store: OsEventStore) -> None:
        self._bus = bus
        self._store = store

    def attach(self) -> None:
        """Se suscribe a TODOS los EventType conocidos del core."""
        for event_type in EventType:
            self._bus.subscribe(event_type, self._on_core_event)

    def _on_core_event(self, event: Event) -> None:
        self._store.append(project_core_event(event))
