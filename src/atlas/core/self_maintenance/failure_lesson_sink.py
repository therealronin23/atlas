"""
Pieza reutilizable: conecta fallos recurrentes del pipeline de autoauditoría
a LessonStore.record_recurring (ver src/atlas/core/lesson_store.py). Un mismo
fallo (misma intención + mismo motivo) no debe generar un archivo de lección
nuevo cada vez que se repite — solo debe subir su occurrence_count.

Ejemplo real del gap que esto cierra (Cónclave, 3ra ronda): el bug de los
YAML se repitió 38 veces y habría generado 38 lecciones casi idénticas sin
ninguna noción de "esto ya lo vi antes N veces".

Punto de wiring real (FUERA DE ALCANCE de este archivo, tarea futura):
`ColdUpdateBatcher._bisect()` (src/atlas/core/cold_update_batcher.py) excluye
una propuesta cuando rompe la suite combinada con
`{"proposal_id": ..., "reason": f"rompe la suite combinada (pytest_exit=...)"}`.
Ese es el punto natural para invocar `FailureLessonSink.record(intent=
proposal.intent, reason=reason)` — pero cablearlo ahí no se hace en esta
tarea, solo se construye la pieza reutilizable.
"""

from __future__ import annotations

import hashlib
from typing import Any


class FailureLessonSink:
    """Registra un fallo recurrente del pipeline de autoauditoría como
    lección con contador de ocurrencias (LessonStore.record_recurring), en
    vez de un archivo nuevo por cada repetición del MISMO fallo. La clave de
    deduplicación es un hash corto y determinista de (intent, reason) —
    misma intención + mismo motivo de fallo = la MISMA lección, cuenta sube.
    Distinta intención o distinto motivo = lección nueva (son fallos
    distintos, no deben mezclarse)."""

    def __init__(self, *, store: Any) -> None:
        self._store = store

    def record(
        self, *, intent: str, reason: str, evidence: dict[str, Any] | None = None
    ) -> Any:
        dedup_key = hashlib.sha256(f"{intent}|{reason}".encode("utf-8")).hexdigest()[:16]
        return self._store.record_recurring(
            dedup_key=dedup_key,
            title=f"Fallo recurrente: {intent[:60]}",
            detection_heuristic=f"Mismo intent+motivo ya visto (dedup_key={dedup_key})",
            avoid_pattern=f"{intent} — motivo: {reason}",
            evidence=evidence or {},
            tags=("self-audit-failure",),
        )
