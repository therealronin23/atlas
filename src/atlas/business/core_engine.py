"""BusinessCoreEngine — draft-first, activación gateada (ADR-061).

Invariante: ningún core pasa a `active` sin pasar por `request_activation`
(→ pending_activation) y `approve_activation` (humano explícito). No hay
atajo de código que salte este camino.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.business.entities import CRM_KINDS, ERP_KINDS
from atlas.business.models import (
    Activation,
    BusinessCore,
    BusinessEntity,
    Canonicality,
    CanonicalityMode,
    CoreStatus,
    CreatedFrom,
    EntityCandidate,
    EntityKind,
    EntityStatus,
    LegacyLink,
    Modules,
)
from atlas.events.emit import emit_event
from atlas.events.schemas import EventStatus, Risk
from atlas.events.store import OsEventStore
from atlas.fabric.gates import GateEngine


class ActivationError(ValueError):
    """Transición de activación inválida (fuera de draft→pending→active)."""


class ReviewRequiredError(ValueError):
    """Se intentó promocionar un candidato sin revisión humana."""


class ModuleDisabledError(ValueError):
    """Se intentó añadir una entidad exclusiva de un módulo (CRM/ERP) que el
    core tiene desactivado. Hace que `modules.crm/erp` no sea decorativo."""


def _default_state_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "business_core" / "state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Store:
    """Persistencia simple de cores/entidades en un único JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {"cores": {}, "entities": {}}
        data: dict[str, dict[str, Any]] = json.loads(
            self._path.read_text(encoding="utf-8")
        )
        return data

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def save_core(self, core: BusinessCore) -> None:
        with self._lock:
            data = self._read()
            data["cores"][core.business_core_id] = core.model_dump(mode="json")
            self._write(data)

    def load_core(self, business_core_id: str) -> BusinessCore | None:
        data = self._read()
        raw = data["cores"].get(business_core_id)
        return BusinessCore.model_validate(raw) if raw else None

    def save_entity(self, entity: BusinessEntity) -> None:
        with self._lock:
            data = self._read()
            data["entities"][entity.entity_id] = entity.model_dump(mode="json")
            self._write(data)

    def entities_for_core(self, business_core_id: str) -> list[BusinessEntity]:
        data = self._read()
        return [
            BusinessEntity.model_validate(e)
            for e in data["entities"].values()
            if e["business_core_id"] == business_core_id
        ]


class BusinessCoreEngine:
    def __init__(
        self,
        store: OsEventStore | None = None,
        path: Path | None = None,
        gate_engine: GateEngine | None = None,
    ) -> None:
        self._events = store
        state_path = path or _default_state_path()
        self._db = _Store(state_path)
        # El Gate Engine hereda el aislamiento del path del core: en tests
        # (tmp_path) los tickets quedan junto al estado, nunca en ~/atlas real.
        self._gates = gate_engine or GateEngine(
            store=store, path=state_path.parent / "gate_tickets.json"
        )

    @property
    def gates(self) -> GateEngine:
        return self._gates

    def create_draft(
        self,
        sector_id: str,
        created_from: CreatedFrom,
        modules: Modules | None = None,
        canonicality: Canonicality | None = None,
        demo: bool = False,
    ) -> BusinessCore:
        core = BusinessCore(
            business_core_id=f"bc_{uuid.uuid4().hex[:10]}",
            sector_id=sector_id,
            status=CoreStatus.DRAFT,
            canonicality=canonicality or Canonicality(
                mode=CanonicalityMode.ATLAS_CANONICAL, source_of_truth="atlas",
            ),
            modules=modules or Modules(crm=True, erp=True),
            entity_ids=[],
            created_from=created_from,
            activation=Activation(gate_id="gate_business_activation", approved=False),
            created_at=_now(),
            updated_at=_now(),
            demo=demo,
        )
        self._db.save_core(core)
        emit_event(
            self._events, "business_core.created",
            f"Business Core draft creado para sector {sector_id}",
            actor="business", source="atlas.business.core_engine",
            payload={"business_core_id": core.business_core_id,
                     "sector_id": sector_id},
        )
        return core

    def get(self, business_core_id: str) -> BusinessCore | None:
        return self._db.load_core(business_core_id)

    def list_entities(self, business_core_id: str) -> list[BusinessEntity]:
        return self._db.entities_for_core(business_core_id)

    def add_entity(
        self,
        business_core_id: str,
        kind: EntityKind,
        label: str,
        data: dict[str, Any] | None = None,
        source_refs: list[str] | None = None,
        requires_review: bool = False,
    ) -> BusinessEntity:
        core = self._require_core(business_core_id)
        if kind in CRM_KINDS and kind not in ERP_KINDS and not core.modules.crm:
            raise ModuleDisabledError(
                f"{kind.value} es una entidad CRM y este core tiene el módulo "
                "CRM desactivado (modules.crm=false)"
            )
        if kind in ERP_KINDS and kind not in CRM_KINDS and not core.modules.erp:
            raise ModuleDisabledError(
                f"{kind.value} es una entidad ERP y este core tiene el módulo "
                "ERP desactivado (modules.erp=false)"
            )
        entity = BusinessEntity(
            entity_id=f"be_{uuid.uuid4().hex[:10]}",
            business_core_id=business_core_id,
            kind=kind,
            label=label,
            status=EntityStatus.DRAFT,
            data=data or {},
            source_refs=source_refs or [],
            requires_review=requires_review,
        )
        self._db.save_entity(entity)
        core.entity_ids.append(entity.entity_id)
        core.updated_at = _now()
        self._db.save_core(core)
        emit_event(
            self._events, "business_core.entity_added",
            f"{kind.value} '{label}' añadido a {business_core_id}",
            actor="business", source="atlas.business.core_engine",
            payload={"business_core_id": business_core_id,
                     "entity_id": entity.entity_id, "kind": kind.value},
        )
        return entity

    def promote_candidate(
        self,
        business_core_id: str,
        candidate: EntityCandidate,
        *,
        reviewed_by: str | None,
    ) -> BusinessEntity:
        """Un EntityCandidate SOLO se convierte en BusinessEntity si un
        humano lo revisó (reviewed_by no vacío). requires_review del
        candidato es const True por contrato — aquí es donde se resuelve."""
        if not reviewed_by:
            raise ReviewRequiredError(
                f"candidato {candidate.candidate_id} no puede promocionarse "
                "sin revisión humana (reviewed_by vacío)"
            )
        entity = self.add_entity(
            business_core_id, candidate.kind, candidate.label,
            data=candidate.proposed_data,
            source_refs=[*candidate.source_refs, f"candidate:{candidate.candidate_id}"],
            requires_review=False,
        )
        emit_event(
            self._events, "business_core.candidate_promoted",
            f"Candidato {candidate.candidate_id} promovido por {reviewed_by}",
            actor="business", source="atlas.business.core_engine",
            payload={"candidate_id": candidate.candidate_id,
                     "entity_id": entity.entity_id, "reviewed_by": reviewed_by},
        )
        return entity

    def request_activation(self, business_core_id: str) -> BusinessCore:
        core = self._require_core(business_core_id)
        if core.status is not CoreStatus.DRAFT:
            raise ActivationError(
                f"{business_core_id} está en {core.status.value}, no en draft"
            )
        # Abre un ticket real en el Gate Engine: 'gated' deja de ser un flag.
        ticket = self._gates.open_ticket(
            gate_id=core.activation.gate_id,
            action="business_core.activate",
            subject_ref=business_core_id,
            risk=Risk.HIGH,
            reason=f"Activar Business Core con {len(core.entity_ids)} entidades",
        )
        core.status = CoreStatus.PENDING_ACTIVATION
        core.activation = core.activation.model_copy(update={
            "gate_ticket_id": ticket.gate_ticket_id,
        })
        core.updated_at = _now()
        self._db.save_core(core)
        emit_event(
            self._events, "business_core.activation.requested",
            f"Activación de {business_core_id} pendiente de aprobación humana",
            actor="business", source="atlas.business.core_engine",
            risk=Risk.HIGH, status=EventStatus.WAITING_USER,
            payload={"business_core_id": business_core_id,
                     "gate_id": core.activation.gate_id,
                     "gate_ticket_id": ticket.gate_ticket_id,
                     "entity_count": len(core.entity_ids)},
        )
        return core

    def approve_activation(
        self, business_core_id: str, approved_by: str,
        decision_note: str | None = None, evidence: list[str] | None = None,
    ) -> BusinessCore:
        core = self._require_core(business_core_id)
        if core.status is not CoreStatus.PENDING_ACTIVATION:
            raise ActivationError(
                f"{business_core_id} no está pending_activation "
                f"(está en {core.status.value}): no se puede activar sin pasar "
                "por request_activation"
            )
        # La aprobación pasa por el Gate Engine (audita quién y cuándo).
        if core.activation.gate_ticket_id is not None:
            self._gates.approve(
                core.activation.gate_ticket_id, resolved_by=approved_by,
                decision_note=decision_note, evidence=evidence,
            )
        core.status = CoreStatus.ACTIVE
        core.activation = core.activation.model_copy(update={
            "approved": True, "approved_by": approved_by, "approved_at": _now(),
        })
        core.updated_at = _now()
        self._db.save_core(core)
        emit_event(
            self._events, "business_core.activated",
            f"Business Core {business_core_id} activado por {approved_by}",
            actor="business", source="atlas.business.core_engine",
            payload={"business_core_id": business_core_id,
                     "approved_by": approved_by,
                     "gate_ticket_id": core.activation.gate_ticket_id},
        )
        return core

    def reject_activation(
        self, business_core_id: str, rejected_by: str,
        decision_note: str | None = None,
    ) -> BusinessCore:
        """Rechazar la activación: el ticket queda rejected y el core vuelve
        a draft (se puede volver a pedir más tarde)."""
        core = self._require_core(business_core_id)
        if core.status is not CoreStatus.PENDING_ACTIVATION:
            raise ActivationError(
                f"{business_core_id} no está pending_activation"
            )
        if core.activation.gate_ticket_id is not None:
            self._gates.reject(
                core.activation.gate_ticket_id, resolved_by=rejected_by,
                decision_note=decision_note,
            )
        core.status = CoreStatus.DRAFT
        core.activation = core.activation.model_copy(update={
            "gate_ticket_id": None,
        })
        core.updated_at = _now()
        self._db.save_core(core)
        emit_event(
            self._events, "business_core.activation.rejected",
            f"Activación de {business_core_id} rechazada por {rejected_by}",
            actor="business", source="atlas.business.core_engine",
            risk=Risk.MEDIUM,
            payload={"business_core_id": business_core_id,
                     "rejected_by": rejected_by},
        )
        return core

    def attach_legacy_link(
        self, business_core_id: str, legacy_link: LegacyLink,
    ) -> BusinessCore:
        core = self._require_core(business_core_id)
        core.legacy_link = legacy_link
        core.updated_at = _now()
        self._db.save_core(core)
        return core

    def _require_core(self, business_core_id: str) -> BusinessCore:
        core = self._db.load_core(business_core_id)
        if core is None:
            raise KeyError(f"business core desconocido: {business_core_id}")
        return core
