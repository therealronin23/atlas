"""
Atlas Core — SqliteLessonIndex: el INQUILINO de ciberseguridad del motor de memoria.

Tras el refactor 2026-06-21, el motor genérico vive en `memory_index.py`
(`SqliteMemoryIndex`, agnóstico de dominio). Este módulo es una vista delgada que
adapta `Lesson` (memoria inmune adversarial) → `MemoryRecord` y delega en el motor.
Conserva la API histórica (índice persistente, `index()`/`rebuild_from(store)`,
`upsert(lesson, ...)`, recall con paridad frente al `LessonRecaller`, enlace Merkle)
para no romper a los consumidores (TeacherDebate vía protocolo `Recaller`).

El texto representativo de una lección = `avoid_pattern` + `detection_heuristic`
(mismo esquema que `LessonRecaller`), de modo que los scores siguen siendo idénticos.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from atlas.immunity.lesson_recaller import RecallResult
from atlas.memory.embeddings import Embedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord, MemoryRecord

if TYPE_CHECKING:
    from atlas.core.lesson_store import Lesson, LessonStore
    from atlas.logging.merkle_logger import MerkleLogger


def lesson_to_record(lesson: Lesson) -> MemoryRecord:
    """Adapta una `Lesson` (seguridad) al contrato genérico del motor.

    El texto representativo sitúa `avoid_pattern` primero (señal más discriminante),
    igual que `LessonRecaller`, para preservar la paridad de scores.
    """
    parts = [lesson.avoid_pattern, lesson.detection_heuristic]
    text = " ".join(p for p in parts if p)
    return GenericRecord(
        record_id=lesson.id,
        text=text,
        created_at=lesson.created_at,
        record_type="empirical",  # las lecciones adversariales son empírico-contingentes
    )


class SqliteLessonIndex:
    """Índice persistente de lecciones de seguridad (inquilino del motor genérico).

    Cumple el protocolo `Recaller` (`index()` + `recall()`) → drop-in del
    `LessonRecaller` in-memory en `TeacherDebate`.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
        store: LessonStore | None = None,
        merkle: "MerkleLogger | None" = None,
        auto_touch: bool = False,
    ) -> None:
        self._engine = SqliteMemoryIndex(
            db_path, embedder=embedder, threshold=threshold,
            merkle=merkle, auto_touch=auto_touch,
        )
        self._store = store

    # ------------------------------------------------------------------
    # Escritura / construcción
    # ------------------------------------------------------------------

    def upsert(
        self,
        lesson: Lesson,
        *,
        merkle_leaf_hash: str | None = None,
        merkle_leaf_index: int | None = None,
    ) -> None:
        self._engine.upsert(
            lesson_to_record(lesson),
            merkle_leaf_hash=merkle_leaf_hash,
            merkle_leaf_index=merkle_leaf_index,
        )

    def rebuild_from(self, store: LessonStore) -> None:
        """Reconstruye el índice desde el CORE (LessonStore). Conserva el orden de
        `store.all()` (created_at desc) para desempates deterministas."""
        self._engine.rebuild_from(lesson_to_record(le) for le in store.all())

    def index(self) -> None:
        """Alias de `rebuild_from(self._store)` para cumplir el protocolo `Recaller`."""
        if self._store is None:
            raise RuntimeError(
                "SqliteLessonIndex.index() requiere construir con store=...; "
                "usa rebuild_from(store) si prefieres pasarlo explícito"
            )
        self.rebuild_from(self._store)

    # ------------------------------------------------------------------
    # Recall + utilidades (delegan en el motor)
    # ------------------------------------------------------------------

    def recall(self, attack_text: str) -> RecallResult | None:
        return self._engine.recall(attack_text)

    def recall_all(self, attack_text: str, k: int = 5) -> list[RecallResult]:
        return self._engine.recall_all(attack_text, k=k)

    # ------------------------------------------------------------------
    # Ciclo de vida de lecciones (delega en el motor adaptando Lesson→record)
    # ------------------------------------------------------------------

    def supersede(
        self, old_lesson_id: str, new_lesson: Lesson, *,
        now_ns: int | None = None, reason: str = "",
    ) -> None:
        """Una lección mejor reemplaza a otra: la vieja caduca (auditable), la
        nueva entra vigente con lineage. Útil cuando una heurística se refina."""
        self._engine.supersede(
            old_lesson_id, lesson_to_record(new_lesson), now_ns=now_ns, reason=reason
        )

    def retire(self, lesson_id: str, *, now_ns: int | None = None, reason: str = "") -> None:
        """Olvido de una lección obsoleta (caduca; no se borra de la cadena)."""
        self._engine.retire(lesson_id, now_ns=now_ns, reason=reason)

    def touch(self, lesson_id: str, *, now_ns: int | None = None) -> None:
        self._engine.touch(lesson_id, now_ns=now_ns)

    def apply_decay(
        self, *, now_ns: int, warm_after_ns: int, cold_after_ns: int,
        pending_after_ns: int, retire_after_ns: int | None = None,
    ) -> dict[str, int]:
        return self._engine.apply_decay(
            now_ns=now_ns, warm_after_ns=warm_after_ns, cold_after_ns=cold_after_ns,
            pending_after_ns=pending_after_ns, retire_after_ns=retire_after_ns,
        )

    def tier(self, lesson_id: str) -> str | None:
        return self._engine.tier(lesson_id)

    def tier_counts(self) -> dict[str, int]:
        return self._engine.tier_counts()

    def active_count(self) -> int:
        return self._engine.active_count()

    def merkle_leaf_hash(self, lesson_id: str) -> str | None:
        return self._engine.merkle_leaf_hash(lesson_id)

    def merkle_leaf_index(self, lesson_id: str) -> int | None:
        return self._engine.merkle_leaf_index(lesson_id)

    def count(self) -> int:
        return self._engine.count()

    def close(self) -> None:
        self._engine.close()
