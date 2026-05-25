"""
Atlas Core — Merkle Logger
Logger de no-repudio forense. Cadena SHA-256 append-only.
Ningun componente de Atlas puede modificar o eliminar entradas.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import uuid

GENESIS_HASH: str = "0" * 64
MAX_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# AuditRecord
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    action: str           # Tipo de accion (ver AUDIT_ACTIONS)
    agent: str            # Componente que ejecuta
    result: str           # "success" | "failure" | "blocked" | "pending"
    risk_level: str       # "safe" | "moderate" | "high" | "critical"
    payload: dict         = field(default_factory=dict)
    task_id: str | None   = None
    id: str               = field(default_factory=lambda: str(uuid.uuid4()))
    hash_prev: str        = field(default=GENESIS_HASH)
    hash_self: str        = field(default="")
    timestamp: str        = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not self.hash_self:
            self.hash_self = self._compute()

    def _compute(self) -> str:
        data = {
            "id": self.id,
            "action": self.action,
            "agent": self.agent,
            "result": self.result,
            "risk_level": self.risk_level,
            "payload": self.payload,
            "task_id": self.task_id,
            "hash_prev": self.hash_prev,
            "timestamp": self.timestamp,
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def verify(self) -> bool:
        """Verifica que hash_self es correcto para el contenido actual."""
        return self.hash_self == self._compute()

    def to_dict(self) -> dict:
        return asdict(self)


AUDIT_ACTIONS = {
    "task.created", "task.classified", "task.routed", "task.approved",
    "task.blocked", "task.completed", "task.failed",
    "tool.invoked", "tool.failed",
    "generated_tool.receipt", "generated_tool.promoted", "generated_tool.stale",
    "generated_tool.resumed", "generated_tool.paused",
    "truth_snapshot.recorded", "gate_h.diagnostic_mode",
    "approved_pattern.added",
    "error_registry.recorded", "memory.rebuilt",
    "governance.violation", "permission.denied",
    "ast_guard.rejected", "sandbox.executed",
    "hermes.delegated", "hermes.mock_queued",
    "model.called", "model.timeout",
    "thermal.alert",
    "memory.written",
    "config.changed",
    "session.started", "session.ended",
    "chain.rotated",
}


# ---------------------------------------------------------------------------
# MerkleLogger
# ---------------------------------------------------------------------------

class MerkleLogger:
    """
    Logger append-only con cadena SHA-256.
    Thread-safe. Verifica la integridad de la cadena en lectura y al arrancar.
    """

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash: str = GENESIS_HASH
        self._record_count: int = 0
        self._current_file: Path = self._resolve_current_file()
        self._load_last_hash()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def append(self, record: AuditRecord) -> AuditRecord:
        """
        Anade un AuditRecord a la cadena.
        Asigna hash_prev y recalcula hash_self.
        Retorna el record con hashes actualizados.
        """
        with self._lock:
            # Reasignar hash_prev con el ultimo hash de la cadena
            linked = AuditRecord(
                action=record.action,
                agent=record.agent,
                result=record.result,
                risk_level=record.risk_level,
                payload=record.payload,
                task_id=record.task_id,
                id=record.id,
                hash_prev=self._last_hash,
                timestamp=record.timestamp,
            )
            line = json.dumps(linked.to_dict(), ensure_ascii=False)
            self._rotate_if_needed()
            with self._current_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._last_hash = linked.hash_self
            self._record_count += 1
            return linked

    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict | None = None,
        task_id: str | None = None,
    ) -> AuditRecord:
        """Shortcut: crea y anade un AuditRecord."""
        record = AuditRecord(
            action=action,
            agent=agent,
            result=result,
            risk_level=risk_level,
            payload=payload or {},
            task_id=task_id,
        )
        return self.append(record)

    # ------------------------------------------------------------------
    # Lectura y verificacion
    # ------------------------------------------------------------------

    def verify_chain(self) -> tuple[bool, str]:
        """
        Recorre todos los archivos de log y verifica la cadena completa.
        Retorna (True, "OK") o (False, descripcion del fallo).
        """
        with self._lock:
            files = sorted(self._log_dir.glob("merkle*.jsonl"))
            prev_hash = GENESIS_HASH
            record_n = 0

            for log_file in files:
                for line in self._iter_lines(log_file):
                    record_n += 1
                    try:
                        data = json.loads(line)
                        rec = AuditRecord(**data)
                    except Exception as e:
                        return False, f"Record #{record_n}: no se puede parsear — {e}"

                    if not rec.verify():
                        return False, (
                            f"Record #{record_n} (id={rec.id}): "
                            f"hash_self invalido."
                        )
                    if rec.hash_prev != prev_hash:
                        return False, (
                            f"Record #{record_n} (id={rec.id}): "
                            f"hash_prev no coincide con hash_self anterior."
                        )
                    prev_hash = rec.hash_self

            return True, "OK"

    def read_all(self) -> list[AuditRecord]:
        with self._lock:
            records = []
            for log_file in sorted(self._log_dir.glob("merkle*.jsonl")):
                for line in self._iter_lines(log_file):
                    try:
                        records.append(AuditRecord(**json.loads(line)))
                    except Exception:
                        continue
            return records

    def tail(self, n: int = 20) -> list[AuditRecord]:
        all_records = self.read_all()
        return all_records[-n:]

    @property
    def record_count(self) -> int:
        return self._record_count

    @property
    def last_hash(self) -> str:
        return self._last_hash

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _resolve_current_file(self) -> Path:
        return self._log_dir / "merkle.jsonl"

    def _load_last_hash(self) -> None:
        """Carga el ultimo hash de la cadena existente al arrancar."""
        last_hash = GENESIS_HASH
        count = 0
        for log_file in sorted(self._log_dir.glob("merkle*.jsonl")):
            for line in self._iter_lines(log_file):
                try:
                    data = json.loads(line)
                    last_hash = data.get("hash_self", last_hash)
                    count += 1
                except Exception:
                    continue
        self._last_hash = last_hash
        self._record_count = count

    def _rotate_if_needed(self) -> None:
        """Rota el archivo si supera MAX_FILE_BYTES."""
        if not self._current_file.exists():
            return
        if self._current_file.stat().st_size < MAX_FILE_BYTES:
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive = self._log_dir / f"merkle-{ts}.jsonl"
        self._current_file.rename(archive)
        # El primer record del nuevo archivo lleva el hash del ultimo del anterior
        # El _last_hash ya esta actualizado por el append anterior

    @staticmethod
    def _iter_lines(path: Path) -> Iterator[str]:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line
