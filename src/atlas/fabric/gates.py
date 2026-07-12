"""GateEngine — ceremonia de decisión humana real (ADR-063).

Convierte "gated" de flag descriptivo en un objeto auditable con ciclo de
vida: open → approved | rejected. Un ticket solo lo resuelve un humano
(resolved_by obligatorio); resolver un ticket ya resuelto es un error.
Persistencia JSON con lock, misma convención que BusinessCoreEngine.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.events.emit import emit_event
from atlas.events.schemas import EventStatus, Risk
from atlas.events.store import OsEventStore
from atlas.fabric.models import GateStatus, GateTicket


class GateTicketError(ValueError):
    """Transición inválida sobre un gate ticket."""


def _default_tickets_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "gates" / "tickets.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GateEngine:
    def __init__(
        self, store: OsEventStore | None = None, path: Path | None = None,
    ) -> None:
        self._events = store
        self._path = path or _default_tickets_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        data: dict[str, dict[str, Any]] = json.loads(
            self._path.read_text(encoding="utf-8")
        )
        return data

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _save(self, ticket: GateTicket) -> None:
        with self._lock:
            data = self._read()
            data[ticket.gate_ticket_id] = ticket.model_dump(mode="json")
            self._write(data)

    def open_ticket(
        self,
        gate_id: str,
        action: str,
        subject_ref: str,
        risk: Risk,
        reason: str,
        requested_by: str = "atlas",
    ) -> GateTicket:
        ticket = GateTicket(
            gate_ticket_id=f"gt_{uuid.uuid4().hex[:10]}",
            gate_id=gate_id,
            action=action,
            subject_ref=subject_ref,
            risk=risk,
            status=GateStatus.OPEN,
            reason=reason,
            requested_by=requested_by,
            requested_at=_now(),
            evidence=[],
        )
        self._save(ticket)
        emit_event(
            self._events, "gate.opened",
            f"Gate {gate_id} abierto para {action} sobre {subject_ref}",
            actor="governance", source="atlas.fabric.gates",
            risk=risk, status=EventStatus.WAITING_USER,
            payload={"gate_ticket_id": ticket.gate_ticket_id, "gate_id": gate_id,
                     "action": action, "subject_ref": subject_ref},
        )
        return ticket

    def get(self, gate_ticket_id: str) -> GateTicket | None:
        raw = self._read().get(gate_ticket_id)
        return GateTicket.model_validate(raw) if raw else None

    def list_open(self) -> list[GateTicket]:
        return [
            GateTicket.model_validate(t) for t in self._read().values()
            if t["status"] == GateStatus.OPEN.value
        ]

    def open_ticket_for_subject(
        self, subject_ref: str, action: str
    ) -> GateTicket | None:
        for raw in self._read().values():
            if (raw["subject_ref"] == subject_ref and raw["action"] == action
                    and raw["status"] == GateStatus.OPEN.value):
                return GateTicket.model_validate(raw)
        return None

    def approve(
        self, gate_ticket_id: str, resolved_by: str,
        decision_note: str | None = None, evidence: list[str] | None = None,
    ) -> GateTicket:
        return self._resolve(gate_ticket_id, GateStatus.APPROVED, resolved_by,
                             decision_note, evidence)

    def reject(
        self, gate_ticket_id: str, resolved_by: str,
        decision_note: str | None = None,
    ) -> GateTicket:
        return self._resolve(gate_ticket_id, GateStatus.REJECTED, resolved_by,
                             decision_note, None)

    def _resolve(
        self, gate_ticket_id: str, status: GateStatus, resolved_by: str,
        decision_note: str | None, evidence: list[str] | None,
    ) -> GateTicket:
        if not resolved_by:
            raise GateTicketError("resolved_by es obligatorio: solo un humano resuelve")
        ticket = self.get(gate_ticket_id)
        if ticket is None:
            raise KeyError(f"gate ticket desconocido: {gate_ticket_id}")
        if ticket.status is not GateStatus.OPEN:
            raise GateTicketError(
                f"{gate_ticket_id} ya está {ticket.status.value}, no se puede "
                f"volver a resolver"
            )
        resolved = ticket.model_copy(update={
            "status": status,
            "resolved_by": resolved_by,
            "resolved_at": _now(),
            "decision_note": decision_note,
            "evidence": evidence or ticket.evidence,
        })
        self._save(resolved)
        emit_event(
            self._events,
            "gate.approved" if status is GateStatus.APPROVED else "gate.rejected",
            f"Gate {ticket.gate_id} ({ticket.action}) {status.value} por {resolved_by}",
            actor="governance", source="atlas.fabric.gates",
            risk=ticket.risk,
            payload={"gate_ticket_id": gate_ticket_id, "status": status.value,
                     "resolved_by": resolved_by, "subject_ref": ticket.subject_ref},
        )
        return resolved
