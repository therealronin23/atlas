"""ADR-039 slice 4 — Scheduler cron del agente de auto-mantenimiento.

Hilo periódico Atlas-side (mismo patrón que ``OfflineMonitor``) que dispara una
pasada del front-half: descubre candidatos (Scout autoritativo), los analiza
(Analyst dual-LLM + gate de corroboración) y **notifica** las propuestas
corroboradas. El cron **jamás aplica**: su única salida es una notificación con
propuestas en estado ``proposed`` esperando el seam del decisor (ADR-040). El
gatillo (adoptar) es del Adopter, no del scheduler.

No posee sus colaboradores: recibe ``discover``/``analyze``/``notify`` por
inyección (callables) → los tests usan fakes y NO tocan red ni LLM (regla del
proyecto). Cadencia configurable; por defecto diaria.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from atlas.core.self_maintenance.candidate import McpCandidate, McpProposal
from atlas.logging.merkle_logger import MerkleLogger

# Cadencia por defecto: una pasada diaria (descubrir/proponer no es urgente).
_DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60


class MaintenanceScheduler:
    """Cron background descubrir→analizar→proponer→notificar. Nunca aplica.

    ``tick()`` ejecuta una pasada y es la unidad testable; ``start()/stop()``
    gestionan el hilo daemon. La adopción real queda fuera: el scheduler solo
    deja propuestas notificadas para el seam del decisor.
    """

    AGENT = "self_maintenance.scheduler"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        discover: Callable[[], list[McpCandidate]],
        analyze: Callable[[McpCandidate], McpProposal | None],
        notify: Callable[[list[McpProposal]], None],
        poll_interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._merkle = merkle
        self._discover = discover
        self._analyze = analyze
        self._notify = notify
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="atlas-maintenance-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — una pasada caída no mata el hilo
                pass
            time.sleep(self._poll_interval)

    def tick(self) -> list[McpProposal]:
        """Una pasada: descubre, analiza, notifica lo corroborado. Nunca aplica."""
        candidates = list(self._discover() or [])
        proposals: list[McpProposal] = []
        for cand in candidates:
            proposal = self._analyze(cand)
            if proposal is not None:
                proposals.append(proposal)

        if proposals:
            try:
                self._notify(proposals)
            except Exception:  # noqa: BLE001 — fallo de notificación no rompe la pasada
                pass

        self._audit(len(candidates), proposals)
        return proposals

    def _audit(self, candidate_count: int, proposals: list[McpProposal]) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.scheduler_tick",
                agent=self.AGENT,
                result="ok",
                risk_level="safe",
                payload={
                    "candidate_count": candidate_count,
                    "proposal_count": len(proposals),
                    "proposal_ids": [p.id for p in proposals],
                    "applied": False,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe la pasada
            pass
