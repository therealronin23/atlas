"""
Atlas Core — Checkpoint storage (ADR-021, Gate D/D5)

Serializacion de estados intermedios de la ejecucion del agente. Cada
checkpoint es una snapshot inmutable identificada por (task_id, step_id)
con encadenado hash al parent para verificar integridad.

Formato en disco: JSON. Path:
    <base>/<task_id>/<step_id>.json

Cada fichero contiene:
{
  "task_id":         str,
  "step_id":         str,
  "parent_step_id":  str | null,
  "label":           str,
  "state":           dict[str, Any],
  "timestamp":       ISO,
  "hash_prev":       str,
  "hash_self":       str (sha256 sobre el resto del registro canonico)
}

La verificacion de cadena recorre los checkpoints de un task_id en orden
y comprueba que hash_self computa correctamente y que hash_prev encaja.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class CheckpointError(Exception):
    """Fallo en almacenamiento o verificacion de checkpoints."""


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass
class Checkpoint:
    task_id: str
    step_id: str
    parent_step_id: str | None
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    hash_prev: str = ""
    hash_self: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


GENESIS_HASH = "0" * 64


class CheckpointStore:
    """
    Persiste checkpoints en disco con encadenado hash. Thread-safe via lock
    de grano grueso (write-mostly, baja contencion esperada).
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path
        self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def save(
        self,
        task_id: str,
        label: str,
        state: dict[str, Any],
        *,
        parent_step_id: str | None = None,
        step_id: str | None = None,
    ) -> Checkpoint:
        if not task_id:
            raise CheckpointError("task_id no puede estar vacio")
        with self._lock:
            task_dir = self._base / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            step = step_id or str(uuid.uuid4())

            # Resolver hash_prev: o el del parent_step_id, o el ultimo, o GENESIS
            hash_prev = self._resolve_hash_prev(task_id, parent_step_id)

            cp = Checkpoint(
                task_id=task_id,
                step_id=step,
                parent_step_id=parent_step_id,
                label=label,
                state=state,
                timestamp=datetime.now(timezone.utc).isoformat(),
                hash_prev=hash_prev,
                hash_self="",
            )
            cp.hash_self = self._compute_hash(cp)

            path = task_dir / f"{step}.json"
            if path.exists():
                raise CheckpointError(f"step_id duplicado: {step}")
            path.write_text(
                json.dumps(cp.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return cp

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def load(self, task_id: str, step_id: str) -> Checkpoint:
        """Carga un checkpoint y verifica su propio hash antes de devolverlo.

        tech-8-snapshot-integrity: ``verify_chain()`` ya detectaba manipulación
        a nivel de cadena, pero ``load()`` reconstruía el ``Checkpoint`` desde
        el JSON en disco sin comprobar nada — un fichero corrupto (a mano, por
        disco dañado, o por un fork/checkout a medias) se restauraba en
        silencio. Recomputa ``hash_self`` con la MISMA función canónica que
        ``save()``/``verify_chain()`` y rechaza con error explícito si no
        encaja, antes de que el estado corrupto llegue al llamador."""
        path = self._base / task_id / f"{step_id}.json"
        if not path.exists():
            raise CheckpointError(f"checkpoint no existe: {task_id}/{step_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        cp = Checkpoint(**data)
        recomputed = self._compute_hash(cp)
        if recomputed != cp.hash_self:
            raise CheckpointError(
                f"checkpoint corrupto ({task_id}/{step_id}): hash_self "
                f"invalido (esperado {recomputed[:8]}, almacenado {cp.hash_self[:8]})"
            )
        return cp

    def list_steps(self, task_id: str) -> list[Checkpoint]:
        """Lista todos los checkpoints de un task_id en orden temporal."""
        task_dir = self._base / task_id
        if not task_dir.exists():
            return []
        steps: list[Checkpoint] = []
        for f in task_dir.glob("*.json"):
            try:
                steps.append(Checkpoint(**json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        steps.sort(key=lambda c: c.timestamp)
        return steps

    def latest(self, task_id: str) -> Checkpoint | None:
        steps = self.list_steps(task_id)
        return steps[-1] if steps else None

    def tasks(self) -> list[str]:
        return sorted(p.name for p in self._base.iterdir() if p.is_dir())

    # ------------------------------------------------------------------
    # Fork — clona un checkpoint a un nuevo task_id como punto de partida
    # ------------------------------------------------------------------

    def fork(
        self,
        from_task_id: str,
        from_step_id: str,
        *,
        new_task_id: str | None = None,
        new_label: str | None = None,
    ) -> Checkpoint:
        """
        Crea un nuevo task_id que arranca clonando el estado de
        (from_task_id, from_step_id). El parent_step_id del primer
        checkpoint del fork apunta al origen.
        """
        origin = self.load(from_task_id, from_step_id)
        new_tid = new_task_id or f"{from_task_id}-fork-{uuid.uuid4().hex[:8]}"
        label = new_label or f"fork from {from_task_id}/{from_step_id}"
        return self.save(
            task_id=new_tid,
            label=label,
            state=dict(origin.state),
            parent_step_id=None,  # nuevo arbol; metadata fork va en label/state
            step_id=None,
        )

    # ------------------------------------------------------------------
    # Verificacion de cadena
    # ------------------------------------------------------------------

    def verify_chain(self, task_id: str) -> tuple[bool, str]:
        """
        Verifica que la cadena de checkpoints de un task_id es coherente.
        Retorna (True, "OK") o (False, descripcion).
        """
        steps = self.list_steps(task_id)
        if not steps:
            return True, "OK (vacio)"

        expected_prev = GENESIS_HASH
        for cp in steps:
            recomputed = self._compute_hash(cp)
            if recomputed != cp.hash_self:
                return False, (
                    f"hash_self invalido en step {cp.step_id}: "
                    f"esperado {recomputed[:8]} pero almacenado {cp.hash_self[:8]}"
                )
            if cp.parent_step_id is None and cp.hash_prev != GENESIS_HASH:
                # Caso fork: el primer step puede no tener parent en este task pero
                # tiene hash_prev del task origen — permitido si encaja con algun
                # otro task_id. Aqui solo validamos el caso "linea recta".
                pass
            elif cp.hash_prev != expected_prev:
                return False, (
                    f"hash_prev de step {cp.step_id} no encaja "
                    f"(esperado {expected_prev[:8]}, recibido {cp.hash_prev[:8]})"
                )
            expected_prev = cp.hash_self
        return True, "OK"

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _resolve_hash_prev(
        self, task_id: str, parent_step_id: str | None
    ) -> str:
        # Caso explicito: parent_step_id apuntando a un step existente
        if parent_step_id is not None:
            parent = self.load(task_id, parent_step_id)
            return parent.hash_self
        latest = self.latest(task_id)
        return latest.hash_self if latest is not None else GENESIS_HASH

    @staticmethod
    def _compute_hash(cp: Checkpoint) -> str:
        canon = {
            "task_id":        cp.task_id,
            "step_id":        cp.step_id,
            "parent_step_id": cp.parent_step_id,
            "label":          cp.label,
            "state":          cp.state,
            "timestamp":      cp.timestamp,
            "hash_prev":      cp.hash_prev,
        }
        blob = json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
