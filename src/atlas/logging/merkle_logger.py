"""
Atlas Core — Merkle Logger
Logger de no-repudio forense. Cadena SHA-256 append-only.
Ningun componente de Atlas puede modificar o eliminar entradas.

Opciones de firma (parametro ``signer`` en el constructor):

- Sin firma (default None): la cadena de hashes detecta corrupcion
  accidental pero NO manipulacion adversarial. Un atacante con acceso al
  sistema de archivos puede reescribir registros y recalcular los hashes.

- Con firma (Signer provisto): cada append() firma el hash_self del nuevo
  registro; verify_chain() verifica cada firma. La contencion real requiere
  que la clave privada este fuera del alcance del atacante (HSM, etc.).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator
import uuid

if TYPE_CHECKING:
    from atlas.security.authorization import Signer

GENESIS_HASH: str = "0" * 64
MAX_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MB
TAIL_READ_BLOCK_BYTES: int = 64 * 1024


# ---------------------------------------------------------------------------
# AuditRecord
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    action: str           # Tipo de accion (ver AUDIT_ACTIONS)
    agent: str            # Componente que ejecuta
    result: str           # "success" | "failure" | "blocked" | "pending"
    risk_level: str       # "safe" | "moderate" | "high" | "critical"
    payload: dict[str, Any] = field(default_factory=dict)
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

    def to_dict(self) -> dict[str, Any]:
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
    "memory.superseded", "memory.retired", "memory.decay",
    "memory.block.created", "memory.block.edited", "memory.block.deleted",
    "config.changed",
    "session.started", "session.ended",
    "chain.rotated", "chain.repaired",
}


# ---------------------------------------------------------------------------
# MerkleLogger
# ---------------------------------------------------------------------------

class MerkleLogger:
    """
    Logger append-only con cadena SHA-256.
    Thread-safe. Verifica la integridad de la cadena en lectura y al arrancar.

    Con ``signer`` provisto: cada append() firma el hash_self y verify_chain()
    verifica las firmas — proteccion contra manipulacion adversarial.

    Sin ``signer`` (default): solo detecta corrupcion accidental, no adversarial.
    """

    def __init__(self, log_dir: Path, signer: Signer | None = None) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._log_dir.chmod(0o700)
        for existing_log in self._log_dir.glob("merkle*.jsonl"):
            if existing_log.is_symlink() or not existing_log.is_file():
                raise ValueError(f"Merkle log is not a regular file: {existing_log}")
            existing_log.chmod(0o600)
        self._lock = threading.Lock()
        self._last_hash: str = GENESIS_HASH
        self._record_count: int = 0
        self._current_file: Path = self._resolve_current_file()
        self._signer: Signer | None = signer
        self._load_last_hash()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def append(self, record: AuditRecord) -> AuditRecord:
        """
        Anade un AuditRecord a la cadena.
        Asigna hash_prev y recalcula hash_self.
        Retorna el record con hashes actualizados.

        Seguro entre procesos: toma un ``flock`` exclusivo sobre el archivo y
        relee el ultimo hash real desde disco antes de encadenar, en vez de
        confiar en ``self._last_hash`` (que queda obsoleto si otro proceso
        escribio mientras tanto). Sin esto, dos escritores concurrentes (p.ej.
        el servicio + un comando CLI) forkean la cadena.
        """
        with self._lock:
            self._rotate_if_needed()
            flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(self._current_file, flags, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError(
                        f"Merkle log is not a regular file: {self._current_file}"
                    )
                os.fchmod(fd, 0o600)
            except Exception:
                os.close(fd)
                raise
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    prev_hash = self._read_last_hash_from_disk()
                    linked = AuditRecord(
                        action=record.action,
                        agent=record.agent,
                        result=record.result,
                        risk_level=record.risk_level,
                        payload=record.payload,
                        task_id=record.task_id,
                        id=record.id,
                        hash_prev=prev_hash,
                        timestamp=record.timestamp,
                    )
                    row = linked.to_dict()
                    if self._signer is not None:
                        row["signature"] = self._signer.sign(linked.hash_self.encode())
                        row["sig_algo"] = self._signer.algo
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            self._last_hash = linked.hash_self
            self._record_count += 1
            return linked

    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict[str, Any] | None = None,
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

        Sin signer: detecta corrupcion accidental (no adversarial).
        Con signer: ademas verifica la firma de cada registro; un registro
        con firma invalida o ausente se considera manipulado adversarialmente.
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
                        # Extraer campos de firma antes de instanciar AuditRecord
                        signature = data.pop("signature", None)
                        data.pop("sig_algo", None)
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

                    # Verificacion de firma si el logger fue configurado con signer
                    if self._signer is not None:
                        if signature is None:
                            return False, (
                                f"Record #{record_n} (id={rec.id}): "
                                f"firma ausente (logger configurado con signer)."
                            )
                        signer = self._signer
                        # Para HMAC simetrico: verificar con la misma clave
                        if hasattr(signer, "_key"):
                            from atlas.security.authorization import HMACVerifier
                            verifier = HMACVerifier(signer._key)
                            if not verifier.verify(rec.hash_self.encode(), signature):
                                return False, (
                                    f"Record #{record_n} (id={rec.id}): "
                                    f"firma invalida — posible manipulacion adversarial."
                                )

                    prev_hash = rec.hash_self

            return True, "OK"

    def read_all(self) -> list[AuditRecord]:
        with self._lock:
            records = []
            for log_file in sorted(self._log_dir.glob("merkle*.jsonl")):
                for line in self._iter_lines(log_file):
                    try:
                        data = json.loads(line)
                        data.pop("signature", None)
                        data.pop("sig_algo", None)
                        records.append(AuditRecord(**data))
                    except Exception:
                        continue
            return records

    def tail(self, n: int = 20) -> list[AuditRecord]:
        # Preserve the historical slicing behavior for zero/negative values.
        # Positive tails take the bounded reverse-reading path below.
        if n <= 0:
            return self.read_all()[-n:]

        with self._lock:
            newest_first: list[AuditRecord] = []
            for log_file in reversed(sorted(self._log_dir.glob("merkle*.jsonl"))):
                for line in self._iter_lines_reverse(log_file):
                    try:
                        data = json.loads(line)
                        data.pop("signature", None)
                        data.pop("sig_algo", None)
                        newest_first.append(AuditRecord(**data))
                    except Exception:
                        continue
                    if len(newest_first) == n:
                        return list(reversed(newest_first))

            return list(reversed(newest_first))

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

    def _read_last_hash_from_disk(self) -> str:
        """Devuelve el hash_self del ultimo record fisico del archivo actual.

        Lee solo la cola del archivo (binario) para no recorrerlo entero. Si el
        archivo no existe o esta vacio (p.ej. justo tras una rotacion), cae al
        ``self._last_hash`` en memoria, que conserva el ultimo hash previo a la
        rotacion; si tampoco lo hay, GENESIS.
        """
        path = self._current_file
        if not path.exists():
            return self._last_hash
        with path.open("rb") as rf:
            size = rf.seek(0, os.SEEK_END)
            if size == 0:
                return self._last_hash
            block = min(size, 131072)
            rf.seek(size - block)
            chunk = rf.read()
        text = chunk.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return self._last_hash
        try:
            return str(json.loads(lines[-1]).get("hash_self", self._last_hash))
        except json.JSONDecodeError:
            return self._last_hash

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

    @staticmethod
    def _iter_lines_reverse(
        path: Path,
        block_size: int = TAIL_READ_BLOCK_BYTES,
    ) -> Iterator[str]:
        """Yield non-empty UTF-8 lines newest-first without loading the file."""
        with path.open("rb") as f:
            position = f.seek(0, os.SEEK_END)
            remainder = b""

            while position > 0:
                read_size = min(block_size, position)
                position -= read_size
                f.seek(position)
                parts = (f.read(read_size) + remainder).split(b"\n")
                remainder = parts[0]
                for line in reversed(parts[1:]):
                    line = line.strip()
                    if line:
                        yield line.decode("utf-8")

            remainder = remainder.strip()
            if remainder:
                yield remainder.decode("utf-8")
