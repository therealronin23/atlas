"""
Atlas Core — TimeTravel API (ADR-021, Gate D/D5)

Wrapper de alto nivel sobre CheckpointStore. Proporciona una API
amigable para grabar pasos de ejecucion, reanudar desde un punto y
crear ramas counterfactuales.

Integra con MerkleLogger: cada save/fork queda registrado en el
audit log con accion `timetravel.checkpoint` o `timetravel.fork`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.core.checkpoint import (
    Checkpoint,
    CheckpointError,
    CheckpointStore,
)
from atlas.logging.merkle_logger import MerkleLogger


@dataclass(frozen=True)
class HistoryEntry:
    """Resumen de un step para listados (sin payload completo)."""

    task_id: str
    step_id: str
    label: str
    timestamp: str
    hash_self: str


class TimeTravel:
    """
    Fachada de orquestacion sobre CheckpointStore + MerkleLogger.

    Uso tipico:

        tt = TimeTravel(store_path=..., merkle=orchestrator._merkle)
        tid = tt.new_task("debug timeout hermes")
        s1 = tt.record_step(tid, "loaded_context", {"chunks": 5})
        s2 = tt.record_step(tid, "inference_called", {"provider": "groq"})

        # Counterfactual: "y si la inferencia hubiera ido a openrouter?"
        branch = tt.fork(tid, s1.step_id, label="what-if openrouter")
        tt.record_step(branch, "inference_called", {"provider": "openrouter"})
    """

    def __init__(self, store_path: Path, merkle: MerkleLogger | None = None) -> None:
        self._store = CheckpointStore(store_path)
        self._merkle = merkle

    # ------------------------------------------------------------------
    # Vida de task
    # ------------------------------------------------------------------

    def new_task(self, label: str, *, task_id: str | None = None) -> str:
        """
        Crea un nuevo task_id y graba un step inicial con label="start".
        Devuelve el task_id.
        """
        tid = task_id or f"tt-{uuid.uuid4().hex[:12]}"
        cp = self._store.save(
            task_id=tid,
            label=f"start: {label}",
            state={"initial_label": label},
        )
        self._log_merkle("timetravel.task_started", cp)
        return tid

    # ------------------------------------------------------------------
    # Pasos
    # ------------------------------------------------------------------

    def record_step(
        self,
        task_id: str,
        label: str,
        state: dict[str, Any],
        *,
        parent_step_id: str | None = None,
    ) -> Checkpoint:
        cp = self._store.save(
            task_id=task_id,
            label=label,
            state=state,
            parent_step_id=parent_step_id,
        )
        self._log_merkle("timetravel.checkpoint", cp)
        return cp

    def resume_from(self, task_id: str, step_id: str) -> dict[str, Any]:
        """
        Devuelve el state del checkpoint. El consumidor decide como
        reanudar la ejecucion a partir de el.
        """
        cp = self._store.load(task_id, step_id)
        return dict(cp.state)

    # ------------------------------------------------------------------
    # Fork (counterfactual)
    # ------------------------------------------------------------------

    def fork(
        self,
        task_id: str,
        step_id: str,
        *,
        new_task_id: str | None = None,
        label: str | None = None,
    ) -> str:
        cp = self._store.fork(
            from_task_id=task_id,
            from_step_id=step_id,
            new_task_id=new_task_id,
            new_label=label,
        )
        self._log_merkle("timetravel.fork", cp, extra={
            "origin_task_id": task_id,
            "origin_step_id": step_id,
        })
        return cp.task_id

    # ------------------------------------------------------------------
    # Listados / verificacion
    # ------------------------------------------------------------------

    def list_history(self, task_id: str) -> list[HistoryEntry]:
        return [
            HistoryEntry(
                task_id=c.task_id,
                step_id=c.step_id,
                label=c.label,
                timestamp=c.timestamp,
                hash_self=c.hash_self,
            )
            for c in self._store.list_steps(task_id)
        ]

    def list_tasks(self) -> list[str]:
        return self._store.tasks()

    def verify_chain(self, task_id: str) -> tuple[bool, str]:
        return self._store.verify_chain(task_id)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _log_merkle(
        self,
        action: str,
        cp: Checkpoint,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        payload: dict[str, Any] = {
            "task_id":  cp.task_id,
            "step_id":  cp.step_id,
            "label":    cp.label,
            "hash":     cp.hash_self,
        }
        if extra:
            payload.update(extra)
        self._merkle.log(
            action=action,
            agent="atlas.timetravel",
            result="ok",
            risk_level="safe",
            payload=payload,
            task_id=cp.task_id,
        )


__all__ = [
    "TimeTravel",
    "HistoryEntry",
    "Checkpoint",
    "CheckpointError",
]
