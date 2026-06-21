"""
Atlas Core — PatternAbstractor: el INQUILINO de ciberseguridad del abstractor genérico.

Tras el refactor 2026-06-21, el motor de abstracción vive en `memory_abstractor.py`
(`MemoryAbstractor`, agnóstico). Este módulo adapta `Lesson` → `MemoryRecord` y
delega. Conserva su API histórica (`abstract(lessons)`, recall sobre patrones,
`assignment()`). `Pattern` y `PatternMatch` se reexportan del motor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.memory.embeddings import Embedder
from atlas.memory.lesson_index import lesson_to_record
from atlas.memory.memory_abstractor import (
    MemoryAbstractor,
    Pattern,
    PatternMatch,
)

if TYPE_CHECKING:
    from atlas.core.lesson_store import Lesson

__all__ = ["Pattern", "PatternMatch", "PatternAbstractor"]


class PatternAbstractor:
    """Agrupa lecciones de seguridad en patrones (inquilino del motor genérico)."""

    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
    ) -> None:
        self._engine = MemoryAbstractor(embedder=embedder, threshold=threshold)

    def abstract(self, lessons: list[Lesson]) -> list[Pattern]:
        return self._engine.abstract([lesson_to_record(le) for le in lessons])

    def assignment(self) -> dict[str, str]:
        return self._engine.assignment()

    @property
    def patterns(self) -> list[Pattern]:
        return self._engine.patterns

    def recall(self, query_text: str) -> PatternMatch | None:
        return self._engine.recall(query_text)

    def recall_all(self, query_text: str, k: int = 5) -> list[PatternMatch]:
        return self._engine.recall_all(query_text, k=k)
