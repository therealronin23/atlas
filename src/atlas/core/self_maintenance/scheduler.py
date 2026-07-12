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
        extra_cycles: tuple[Callable[[], None], ...] = (),
    ) -> None:
        self._merkle = merkle
        self._discover = discover
        self._analyze = analyze
        self._notify = notify
        self._poll_interval = poll_interval_seconds
        # Ciclos adicionales que el cron corre tras la pasada MCP (p.ej. bumps de
        # deps → ColdUpdate). Genéricos: el scheduler los invoca, no sabe qué
        # hacen. Cada uno es aislado (un fallo no rompe los demás ni el tick).
        self._extra_cycles = tuple(extra_cycles)
        self._running = False
        self._thread: threading.Thread | None = None
        # Señal de parada cooperativa (incidente 2026-07-09): un hilo que
        # sobrevive al join(timeout=2) de stop() seguía arrancando extra_cycles
        # DESPUÉS de que el test deshiciera sus monkeypatches → un run_item
        # real desde una suite. El evento corta los ciclos aún no arrancados;
        # el ciclo ya en vuelo es irreducible sin cancelación dentro del tick.
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="atlas-maintenance-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        # Despierta el sleep del loop al instante y veta los extra_cycles que
        # aún no hayan arrancado (antes: time.sleep ciego + join 2s y el hilo
        # seguía vivo con el tick entero por delante).
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — una pasada caída no mata el hilo
                pass
            if self._stop_event.wait(self._poll_interval):
                return

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

        # Ciclos adicionales (deps/codegen): aislados, posteriores a la pasada
        # MCP. Cada uno gobierna su propia adopción tras el seam del decisor.
        for cycle in self._extra_cycles:
            if self._stop_event.is_set():
                # stop() en vuelo: no arrancar más ciclos. Un tick() directo
                # (sin start/stop) tiene el evento limpio y los corre todos.
                break
            try:
                cycle()
            except Exception:  # noqa: BLE001 — un ciclo caído no rompe los demás
                pass

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
