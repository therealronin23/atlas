"""Gestión de pending approvals (HITL) — Gate C/C4-s2 + ADR-032/033.

Extraído de ``Orchestrator`` (refactor god-object slice 5/D, 2026-05-31).
Sin cambios de comportamiento: solo movimiento físico + centralización de la
propiedad del registro en memoria de approvals pendientes.

Responsabilidad única: ser el dueño del diccionario en memoria de tasks que
esperan aprobación humana (``register``/``snapshot``/``discard``) y ejecutar el
veredicto humano (``approve``). La ejecución real del task aprobado y la
reanudación del loop agéntico viven todavía en ``Orchestrator`` y se inyectan
como callbacks (``on_execute`` / ``on_resume``) para romper el ciclo de import.
"""

from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path
from typing import Callable

from atlas.core.contracts import Task, TaskStatus
from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
from atlas.governance.permission_profile import PermissionProfile
from atlas.logging.merkle_logger import MerkleLogger


class ApprovalManager:
    """Dueño del registro de pending approvals + flujo approve/deny (HITL)."""

    def __init__(
        self,
        *,
        pending_dir: Path,
        tasks: TaskPersistence,
        merkle: MerkleLogger,
        permissions: PermissionProfile,
        on_execute: Callable[[Task], None],
        on_resume: Callable[[Task], None],
    ) -> None:
        self._dir = pending_dir
        self._tasks = tasks
        self._merkle = merkle
        self._permissions = permissions
        self._on_execute = on_execute
        self._on_resume = on_resume
        self._pending: dict[str, Task] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------- registro en memoria

    def register(self, task: Task) -> None:
        """Apunta un task suspendido como pendiente de aprobación."""
        with self._lock:
            self._pending[task.id] = task

    def discard(self, task_id: str) -> None:
        """Quita un task del registro en memoria (idempotente)."""
        with self._lock:
            self._pending.pop(task_id, None)

    def snapshot(self) -> list[Task]:
        """Copia de los tasks pendientes en memoria (para barridos externos)."""
        with self._lock:
            return list(self._pending.values())

    # --------------------------------------------------------------- consultas

    def pending(self) -> list[dict]:
        with self._lock:
            tasks = dict(self._pending)
        for task in self._tasks.load_all():
            tasks.setdefault(task.id, task)
        return [TaskPersistence.summary(t) for t in tasks.values()]

    # --------------------------------------------------------------- veredicto

    def approve(
        self,
        task_id: str,
        approved: bool,
        *,
        abort: bool = False,
        approve_only: list[str] | None = None,
    ) -> dict:
        lock_fd, lock_path = self._tasks.acquire_lock(task_id)
        if lock_fd is None:
            return {
                "task_id": task_id,
                "status": "in_progress",
                "error": "otro proceso esta aprobando o ejecutando esta tarea",
            }
        try:
            return self._approve_locked(
                task_id, approved, abort=abort, approve_only=approve_only,
            )
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            if lock_path is not None:
                lock_path.unlink(missing_ok=True)

    def _approve_locked(
        self,
        task_id: str,
        approved: bool,
        *,
        abort: bool = False,
        approve_only: list[str] | None = None,
    ) -> dict:
        with self._lock:
            task = self._pending.pop(task_id, None)

        pending_path = self._dir / f"{task_id}.json"
        executing_path = self._dir / f"{task_id}.executing.json"

        if executing_path.exists():
            return {
                "task_id": task_id,
                "status": "in_progress",
                "error": "la tarea ya esta en ejecucion",
            }

        if task is None:
            if pending_path.exists():
                task = self._tasks.load(task_id)
            else:
                task = None

        if task is None:
            return {
                "task_id": task_id,
                "status": "unknown",
                "error": "no pending approval with this id",
            }

        self._merkle.log(
            action="task.approval",
            agent="orchestrator",
            result="approved" if approved else "denied",
            risk_level="high",
            payload={"approved": approved},
            task_id=task.id,
        )

        is_agentic = isinstance(task.metadata.get("agentic_state"), dict)

        if not approved:
            # ADR-032 dec.6/7: para un loop suspendido, un DENY sin abort inyecta
            # una denegación sintética y REANUDA (presión MemGPT → el modelo
            # re-planifica). Con abort=True (o tarea no-agéntica) → CANCELLED.
            if is_agentic and not abort:
                state = task.metadata["agentic_state"]
                state["denied"] = True
                state["deny_reason"] = "human"
                try:
                    pending_path.replace(executing_path)
                except OSError as exc:
                    return {
                        "task_id": task_id,
                        "status": "failed",
                        "error": f"no se pudo reservar ejecucion: {exc}",
                    }
                # No mark_confirmed: las mutaciones denegadas no se ejecutan; se
                # inyecta una denegación sintética y el modelo re-planifica.
                task.transition(TaskStatus.EXECUTING)
                resuspended = False
                try:
                    self._on_resume(task)
                    resuspended = task.status == TaskStatus.AWAITING_APPROVAL
                except Exception as e:  # noqa: BLE001
                    task.transition(TaskStatus.FAILED)
                    task.error = str(e)
                finally:
                    executing_path.unlink(missing_ok=True)
                    if not resuspended:
                        pending_path.unlink(missing_ok=True)
                return {
                    "task_id": task.id,
                    "status": task.status.value,
                    "approved": False,
                    "denied_and_resumed": True,
                    "result": task.result,
                }
            task.transition(TaskStatus.CANCELLED)
            task.result = {"approved": False, "message": "Usuario rechazo la accion."}
            self._tasks.delete(task.id)
            return {"task_id": task.id, "status": task.status.value, "approved": False}

        try:
            pending_path.replace(executing_path)
        except OSError as exc:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"no se pudo reservar ejecucion: {exc}",
            }

        # ADR-033 #3: aprobación parcial. Si el llamante pasa `approve_only`, solo
        # esas tool_call ids del lote se ejecutan; el resto recibe denegación
        # sintética al reanudar. Sin `approve_only` → se aprueba el lote entero.
        if is_agentic and approve_only is not None:
            task.metadata["agentic_state"]["approve_only"] = list(approve_only)

        self._permissions.mark_confirmed(f"task:{task.id}")
        task.transition(TaskStatus.EXECUTING)
        # ADR-032: si el loop se vuelve a suspender (otra mutación más adelante),
        # NO borramos el nuevo <id>.json que AgenticExecutor._suspend acaba de
        # persistir; solo limpiamos la reserva .executing.
        resuspended = False
        try:
            self._on_execute(task)
            resuspended = task.status == TaskStatus.AWAITING_APPROVAL
        except Exception as e:
            task.transition(TaskStatus.FAILED)
            task.error = str(e)
        finally:
            executing_path.unlink(missing_ok=True)
            if not resuspended:
                pending_path.unlink(missing_ok=True)

        return {
            "task_id": task.id,
            "status": task.status.value,
            "approved": True,
            "result": task.result,
        }
