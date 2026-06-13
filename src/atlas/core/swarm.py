"""
Capa 3 — Enjambre sobre blackboard (ADR-045).

N workers coordinados por **artefactos verificables**, no por contexto
compartido. Cada worker produce un `Artifact`; nada aterriza en el blackboard
sin pasar por el seam de la capa 1 (`UniversalVerifier`): la ley del blackboard
es la misma de todo Atlas — sin `Evidence` PASS, no se acepta.

El `SwarmCoordinator` asigna **envelopes** (presupuesto, dominio, duración) y
decide POLÍTICAS, no acciones: los workers actúan, el coordinador acota y
audita por muestreo. Si el coordinador aprobara cada acción sería el cuello de
botella (HITL con otro nombre). Reusa la `CostLedger` de la capa 2 para la
métrica de coste por resultado verificado.

El aislamiento real (worktree por worker) es responsabilidad del backend del
worker, modelado tras la interfaz `Worker`: el coordinador no comparte estado
con ellos. Esta iteración es la librería de coordinación; no lanza procesos ni
worktrees reales (en tests, workers fake).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from atlas.core.verify import Artifact, Evidence, UniversalVerifier, Verdict
from atlas.logging.merkle_logger import MerkleLogger
from atlas.router.cascade import CostLedger


@dataclass(frozen=True)
class Envelope:
    """Política asignada por el decider: qué dominio, cuánto presupuesto, hasta
    cuándo. Presupuesto en unidades ordinales de tier (como `CostLedger`)."""

    worker_id: str
    domain: str
    budget_units: int
    expires_at: str  # ISO-8601 UTC

    def is_expired(self, now: datetime | None = None) -> bool:
        ref = now or datetime.now(timezone.utc)
        try:
            exp = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True  # fecha inválida = caducado (fail-closed)
        return ref >= exp


class EntryStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BlackboardEntry:
    id: str
    worker_id: str
    domain: str
    status: EntryStatus
    evidence: dict[str, Any]
    artifact_kind: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "worker_id": self.worker_id,
            "domain": self.domain,
            "status": self.status.value,
            "evidence": self.evidence,
            "artifact_kind": self.artifact_kind,
            "created_at": self.created_at,
        }


class Blackboard:
    """Log append-only de artefactos verificados. La ley: un artefacto se
    ACEPTA solo si su `Evidence` es PASS; si no, se registra REJECTED (queda en
    el rastro de auditoría, no se descarta en silencio)."""

    def __init__(self, *, merkle: MerkleLogger | None = None) -> None:
        self._entries: list[BlackboardEntry] = []
        self._merkle = merkle

    def submit(
        self, *, worker_id: str, domain: str, artifact: Artifact, evidence: Evidence
    ) -> BlackboardEntry:
        accepted = evidence.verdict is Verdict.PASS
        entry = BlackboardEntry(
            id=f"bb-{uuid.uuid4().hex[:12]}",
            worker_id=worker_id,
            domain=domain,
            status=EntryStatus.ACCEPTED if accepted else EntryStatus.REJECTED,
            evidence=evidence.to_dict(),
            artifact_kind=artifact.kind.value,
        )
        self._entries.append(entry)
        if self._merkle is not None:
            self._merkle.log(
                action="blackboard.submit",
                agent=f"worker:{worker_id}",
                result="success" if accepted else "blocked",
                risk_level="safe",
                payload=entry.to_dict(),
            )
        return entry

    def all(self) -> list[BlackboardEntry]:
        return list(self._entries)

    def accepted(self) -> list[BlackboardEntry]:
        return [e for e in self._entries if e.status is EntryStatus.ACCEPTED]

    def rejected(self) -> list[BlackboardEntry]:
        return [e for e in self._entries if e.status is EntryStatus.REJECTED]


class Worker(Protocol):
    @property
    def worker_id(self) -> str: ...

    @property
    def domain(self) -> str: ...

    def produce(self, task: Any) -> Artifact: ...


@dataclass(frozen=True)
class RoundResult:
    accepted: tuple[BlackboardEntry, ...]
    rejected: tuple[BlackboardEntry, ...]
    skipped: tuple[str, ...]  # worker_ids saltados (envelope caducado o sin presupuesto)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": [e.to_dict() for e in self.accepted],
            "rejected": [e.to_dict() for e in self.rejected],
            "skipped": list(self.skipped),
        }


class SwarmCoordinator:
    """Asigna envelopes, corre rondas y audita por muestreo. Decide políticas,
    no acciones: cada artefacto de worker pasa por el verificador de capa 1 y
    cuenta contra el presupuesto del envelope vía la `CostLedger` de capa 2."""

    def __init__(
        self,
        verifier: UniversalVerifier,
        blackboard: Blackboard,
        *,
        ledger: CostLedger | None = None,
        on_accepted: Callable[[BlackboardEntry, Artifact], None] | None = None,
    ) -> None:
        self._verifier = verifier
        self._blackboard = blackboard
        self.ledger = ledger or CostLedger()
        # Hook de reconciliación (política inyectada, PDP): se invoca por cada
        # artefacto ACEPTADO. El ColdUpdateReconciler lo usa para crear una
        # propuesta — NUNCA auto-aplica aquí (eso lo decide el decider).
        self._on_accepted = on_accepted
        self._assignments: dict[str, tuple[Worker, Envelope]] = {}
        self._spent: dict[str, int] = {}

    def assign(self, worker: Worker, envelope: Envelope) -> None:
        if worker.worker_id != envelope.worker_id:
            raise ValueError(
                f"envelope para {envelope.worker_id!r} asignado a worker {worker.worker_id!r}"
            )
        self._assignments[worker.worker_id] = (worker, envelope)
        self._spent.setdefault(worker.worker_id, 0)

    def remaining_budget(self, worker_id: str) -> int:
        _, envelope = self._assignments[worker_id]
        return envelope.budget_units - self._spent.get(worker_id, 0)

    def run_round(
        self, tasks: dict[str, Any], *, now: datetime | None = None
    ) -> RoundResult:
        """Una ronda: cada worker con tarea, envelope vigente y presupuesto
        produce → se verifica (capa 1) → aterriza en el blackboard si PASS. El
        coste del intento (productor + verificación) descuenta del envelope."""
        accepted: list[BlackboardEntry] = []
        rejected: list[BlackboardEntry] = []
        skipped: list[str] = []

        for worker_id, task in tasks.items():
            assignment = self._assignments.get(worker_id)
            if assignment is None:
                skipped.append(worker_id)
                continue
            worker, envelope = assignment
            if envelope.is_expired(now) or self.remaining_budget(worker_id) <= 0:
                skipped.append(worker_id)
                continue

            artifact = worker.produce(task)
            evidence = self._verifier.verify(artifact)
            cost = int(artifact.producer_cost) + int(evidence.total_cost)
            self._spent[worker_id] = self._spent.get(worker_id, 0) + cost
            self.ledger.record_attempt(artifact.producer_cost, evidence.total_cost)

            entry = self._blackboard.submit(
                worker_id=worker_id, domain=envelope.domain,
                artifact=artifact, evidence=evidence,
            )
            if entry.status is EntryStatus.ACCEPTED:
                self.ledger.record_verified()
                accepted.append(entry)
                if self._on_accepted is not None:
                    self._on_accepted(entry, artifact)
            else:
                rejected.append(entry)

        return RoundResult(
            accepted=tuple(accepted), rejected=tuple(rejected), skipped=tuple(skipped)
        )

    def audit_sample(
        self, fraction: float, *, rng_seed: int = 0
    ) -> list[BlackboardEntry]:
        """Muestra determinista de entradas ACEPTADAS para re-verificación. El
        coordinador audita por muestreo + Merkle, no revisa todo (o sería el
        cuello de botella). `fraction` en [0,1]."""
        import random

        accepted = self._blackboard.accepted()
        if not accepted or fraction <= 0:
            return []
        if fraction >= 1:
            return list(accepted)
        k = max(1, round(len(accepted) * fraction))
        rng = random.Random(rng_seed)
        return rng.sample(accepted, k)
