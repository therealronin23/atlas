"""Helper de emisión para motores OS (fabric/business): un solo sitio donde
se construye OsEvent fuera del bridge. store=None → no-op que devuelve el
evento sin persistir (útil en tests puros)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from atlas.events.schemas import EventStatus, OsEvent, Risk
from atlas.events.store import OsEventStore


def emit_event(
    store: OsEventStore | None,
    type_: str,
    summary: str,
    *,
    actor: str,
    source: str,
    status: EventStatus = EventStatus.COMPLETED,
    risk: Risk = Risk.LOW,
    payload: dict[str, Any] | None = None,
    simulated: bool = True,
) -> OsEvent:
    event = OsEvent(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        type=type_,
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
        actor=actor,
        summary=summary,
        status=status,
        risk=risk,
        visible=True,
        simulated=simulated,
        payload=payload or {},
    )
    if store is not None:
        return store.append(event)
    return event
