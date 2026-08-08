"""Single-writer guard para la cadena Merkle de un workspace.

``MerkleLogger.append`` ya es seguro entre procesos a nivel de registro
(flock por escritura + relectura del último hash), pero dos escritores de
larga vida sobre el mismo ``ATLAS_HOME`` siguen siendo un error operacional:
la rotación de archivos no está coordinada entre procesos y los lazos
autónomos asumen que son el único auditor (origen: 2026-06-12, un self-audit
de 24h sin aislar corrió 15 ciclos junto a ``atlas serve``).

Este guard lo convierte en imposible en vez de en disciplina: los entrypoints
escritores (``serve``, ``self-audit run``) toman un ``flock`` exclusivo sobre
``memory/audit/.writer.lock`` durante toda su vida. El lock lo libera el
kernel al morir el proceso, así que no existen locks stale; el contenido del
archivo (pid + timestamp) es solo diagnóstico para el mensaje de error.

Sin ``--force`` a propósito: si de verdad hay que saltárselo, se mata al
escritor activo. Borrar el archivo no libera nada (el lock vive en el fd).
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


__all__ = [
    "ExclusiveWriterLock",
    "MerkleWriterLock",
    "ProjectGraphWriterLock",
    "WriterLockHeld",
]


class WriterLockHeld(RuntimeError):
    """Otro proceso ya es el escritor de este recurso."""


class ExclusiveWriterLock:
    """Lock de escritor único sobre un recurso, por ``flock``.

    Extraído de ``MerkleWriterLock`` el 2026-08-08 sin cambiarle el
    comportamiento: el mismo guard hacía falta para la reconstrucción del grafo
    y duplicarlo habría sido peor que compartirlo.

    El motivo de la extracción es un incidente real. ``graph-rebuild-single-writer``
    llevaba desde siempre declarada como manía en ``AGENTS.md`` y en ningún
    sitio más; dos ticks del grafo concurrentes dejaron la BD Kuzu con las
    tablas del callgraph y sin las bitemporales. Aplica literalmente el docstring
    de este módulo: convertirlo en imposible en vez de en disciplina. Una regla
    que sólo vive en un documento es una regla que se rompe.

    Uso como context manager o con ``acquire()`` explícito para procesos que lo
    retienen hasta morir (serve, self-audit).
    """

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fh: IO[str] | None = None

    @property
    def path(self) -> Path:
        return self._lock_path

    def acquire(self) -> None:
        """Toma el lock o lanza ``WriterLockHeld`` con el escritor actual."""
        if self._fh is not None:
            return
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            holder = self._read_holder(fh)
            fh.close()
            raise WriterLockHeld(
                f"otro escritor activo sobre {self._lock_path.parent}: {holder}. "
                f"{self._hint}"
            ) from None
        fh.seek(0)
        fh.truncate()
        fh.write(
            json.dumps(
                {"pid": os.getpid(), "since": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            )
        )
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        if self._fh is None:
            return
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        self._fh.close()
        self._fh = None

    def __enter__(self) -> ExclusiveWriterLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    #: Qué hacer al chocar. Cada recurso tiene su salida distinta.
    _hint = "Detén ese proceso."

    @staticmethod
    def _read_holder(fh: IO[str]) -> str:
        try:
            fh.seek(0)
            data = json.loads(fh.read() or "{}")
            return f"PID {data.get('pid', '?')} desde {data.get('since', '?')}"
        except (json.JSONDecodeError, OSError):
            return "desconocido"


class MerkleWriterLock(ExclusiveWriterLock):
    """El lock de siempre sobre el audit dir de un workspace."""

    _hint = "Detén ese proceso o usa un ATLAS_HOME aislado."

    def __init__(self, workspace: Path) -> None:
        super().__init__(
            workspace.expanduser().resolve() / "memory" / "audit" / ".writer.lock"
        )


class ProjectGraphWriterLock(ExclusiveWriterLock):
    """Escritor único de la BD Kuzu del grafo del proyecto.

    Kuzu no es seguro multi-proceso para escritura: el 2026-08-08 dos ticks
    solapados dejaron el catálogo a medias (sobrevivieron Symbol/CALLS/CONTAINS,
    desaparecieron FileVersion/Module/IMPORTS). No hubo pérdida real porque el
    grafo es derivado y se reconstruye de git+AST, pero el diagnóstico costó
    caro y el fallo era evitable.

    El lock va junto a la BD, no bajo el workspace: ``db_path`` es inyectable
    (``ATLAS_GRAPH_DB``), así que dos BDs distintas son dos escritores legítimos
    y bloquearlos entre sí sería un falso positivo.
    """

    _hint = "Espera a que termine esa reconstrucción; el grafo admite un solo escritor."

    def __init__(self, db_path: Path) -> None:
        resolved = Path(db_path).expanduser()
        super().__init__(resolved.parent / f".{resolved.name}.writer.lock")
