"""Persistencia de tasks suspendidos en AWAITING_APPROVAL.

Extraído de ``Orchestrator`` (refactor god-object slice 1, 2026-05-30).
Sin cambios de comportamiento ni de formato JSON — solo movimiento físico.

Responsabilidad: serializar/deserializar ``Task``, escribir/leer/borrar el
sobre HMAC en disco y mantener un lock por task. Toda falla se registra en
Merkle pero no se propaga (el flujo del orquestador no debe romperse por
problemas de disco accesorios).
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.contracts import (
    OperationalMode,
    RoutingLevel,
    Task,
    TaskSource,
    TaskStatus,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.pending_store import (
    is_legacy_pending_file,
    unwrap_task_payload,
    wrap_task_payload,
)


class TaskPersistence:
    """I/O de pending approvals + (de)serialización de ``Task``."""

    def __init__(self, pending_dir: Path, merkle: MerkleLogger) -> None:
        self._dir = pending_dir
        self._quarantine_dir = pending_dir / "_quarantine"
        self._merkle = merkle

    # ------------------------------------------------------------------ summary

    @staticmethod
    def summary(task: Task) -> dict:
        """Resumen consumido por CLI/Telegram/dashboard.

        ADR-033: si es un loop agéntico suspendido, expone las mutaciones
        pendientes para que la UI pueda ofrecer aprobación parcial.
        """
        summary = {
            "task_id": task.id,
            "intent": task.intent,
            "reason": (task.result or {}).get("reason", "") if isinstance(task.result, dict) else "",
            "tool": task.tool_name,
            "route": task.route.value if task.route else None,
            "created_at": task.created_at,
        }
        state = task.metadata.get("agentic_state")
        if isinstance(state, dict):
            muts = state.get("pending_mutations") or []
            summary["agentic"] = True
            summary["pending_mutations"] = [
                {"id": m.get("id"), "name": m.get("name")} for m in muts
            ]
        return summary

    # ------------------------------------------------------------------ quarantine

    def _quarantine(self, path: Path, *, reason: str) -> None:
        task_id = path.stem
        try:
            self._quarantine_dir.mkdir(parents=True, exist_ok=True)
            dest = self._quarantine_dir / path.name
            if dest.exists():
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                dest = self._quarantine_dir / f"{path.stem}_{ts}{path.suffix}"
            path.rename(dest)
            self._merkle.log(
                action="approval.quarantined",
                agent="orchestrator",
                result="success",
                risk_level="high",
                payload={"task_id": task_id, "reason": reason, "quarantine_path": str(dest)},
                task_id=task_id,
            )
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.quarantine_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task_id, "reason": reason, "error": str(exc)[:500]},
                task_id=task_id,
            )

    # ------------------------------------------------------------------ persist

    def persist(self, task: Task) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{task.id}.json"
            envelope = wrap_task_payload(self.serialize(task))
            path.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._merkle.log(
                action="approval.persisted",
                agent="orchestrator",
                result="success",
                risk_level="safe",
                payload={"task_id": task.id, "path": str(path)},
                task_id=task.id,
            )
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.persist_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task.id, "error": str(exc)[:500]},
                task_id=task.id,
            )

    def load(self, task_id: str) -> Task | None:
        path = self._dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("pending file is not a JSON object")
            if is_legacy_pending_file(raw):
                self._merkle.log(
                    action="approval.legacy_rejected",
                    agent="orchestrator",
                    result="failure",
                    risk_level="high",
                    payload={
                        "task_id": task_id,
                        "hint": "re-submit task; pending v1 requires HMAC envelope",
                    },
                    task_id=task_id,
                )
                self._quarantine(path, reason="legacy")
                return None
            task_data = unwrap_task_payload(raw)
            if task_data is None:
                self._merkle.log(
                    action="approval.tamper_detected",
                    agent="orchestrator",
                    result="failure",
                    risk_level="critical",
                    payload={"task_id": task_id, "path": str(path)},
                    task_id=task_id,
                )
                self._quarantine(path, reason="mac_mismatch")
                return None
            return self.deserialize(task_data)
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.load_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task_id, "error": str(exc)[:500]},
            )
            return None

    def load_all(self) -> list[Task]:
        if not self._dir.exists():
            return []
        tasks: list[Task] = []
        for path in sorted(self._dir.glob("*.json")):
            if ".executing" in path.name or path.name.startswith("_"):
                continue
            task = self.load(path.stem)
            if task is not None:
                tasks.append(task)
        return tasks

    def delete(self, task_id: str) -> None:
        try:
            (self._dir / f"{task_id}.json").unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            self._merkle.log(
                action="approval.delete_failed",
                agent="orchestrator",
                result="failure",
                risk_level="moderate",
                payload={"task_id": task_id, "error": str(exc)[:500]},
            )

    # ------------------------------------------------------------------ lock

    def acquire_lock(
        self, task_id: str
    ) -> tuple[int, Path] | tuple[None, None]:
        self._dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._dir / f"{task_id}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None, None
        return fd, lock_path

    # ------------------------------------------------------------------ codec

    @staticmethod
    def serialize(task: Task) -> dict:
        data = task.to_dict()
        data["operational_mode"] = task.operational_mode.value
        data["metadata"] = task.metadata
        return data

    @staticmethod
    def deserialize(data: dict[str, Any]) -> Task:
        task = Task(
            intent=str(data["intent"]),
            source=TaskSource(str(data.get("source", TaskSource.CLI.value))),
            id=str(data["id"]),
            priority=int(data.get("priority", 3)),
            sensitivity=str(data.get("sensitivity", "low")),
            action=str(data.get("action", "")),
            operational_mode=OperationalMode(
                str(data.get("operational_mode", OperationalMode.NORMAL.value))
            ),
            parent_id=data.get("parent_id"),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            metadata=dict(data.get("metadata") or {}),
        )
        task.status = TaskStatus(str(data.get("status", TaskStatus.AWAITING_APPROVAL.value)))
        route = data.get("route")
        task.route = RoutingLevel(str(route)) if route else None
        task.tool_name = data.get("tool_name")
        task.result = data.get("result")
        task.error = data.get("error")
        task.audit_hash = data.get("audit_hash")
        return task
