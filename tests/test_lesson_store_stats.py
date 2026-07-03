"""
Tests de verificación para LessonStore.stats() — usados como criterio real de
éxito de los incrementos del IncrementalCoder (lección del experimento sandbox:
el test debe ejercitar la feature, no solo "no romper nada").
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.lesson_store import (
    Lesson,
    LessonProvenance,
    LessonStore,
)
from atlas.core.verify import Verdict


def _lesson(lesson_id: str, provenance: LessonProvenance) -> Lesson:
    return Lesson(
        id=lesson_id,
        title=f"lección {lesson_id}",
        detection_heuristic="h",
        avoid_pattern="p",
        provenance=provenance,
        evidence={"verdict": Verdict.PASS.value},
        source_refs=(),
        tags=(),
    )


def test_stats_empty_store(tmp_path: Path) -> None:
    store = LessonStore(tmp_path / "lessons")
    stats = store.stats()
    assert stats == {"total": 0, "by_provenance": {}}


def test_stats_counts_by_provenance(tmp_path: Path) -> None:
    store = LessonStore(tmp_path / "lessons")
    store.add(_lesson("a", LessonProvenance.INTERNAL_FAILURE))
    store.add(_lesson("b", LessonProvenance.INTERNAL_FAILURE))
    store.add(_lesson("c", LessonProvenance.EXTERNAL_SOURCE))

    stats = store.stats()
    assert stats["total"] == 3
    assert stats["by_provenance"]["internal_failure"] == 2
    assert stats["by_provenance"]["external_source"] == 1
