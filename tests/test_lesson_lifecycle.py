"""
Capa 4 — ciclo de vida de Lesson por uso real (recall_count/state), patrón
absorbido de Hermes-Agent (agent/curator.py::apply_automatic_transitions,
2026-07-18). Sin red, sin subprocesos reales — todo en tmp_path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.core.lesson_store import (
    Lesson,
    LessonProvenance,
    LessonStore,
)


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


def _make_lesson(store: LessonStore, *, created_at: str = "") -> Lesson:
    lesson = Lesson(
        id="lesson-1",
        title="evita X",
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic="detecta X",
        avoid_pattern="no hagas X",
        evidence={"verdict": "pass"},
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )
    store.add(lesson)
    return lesson


class TestRecordRecall:
    def test_increments_recall_count_and_sets_timestamp(self, store: LessonStore) -> None:
        _make_lesson(store)
        updated = store.record_recall("lesson-1")
        assert updated is not None
        assert updated.recall_count == 1
        assert updated.last_recalled_at != ""

        again = store.record_recall("lesson-1")
        assert again.recall_count == 2

    def test_persists_to_disk(self, store: LessonStore) -> None:
        _make_lesson(store)
        store.record_recall("lesson-1")
        reloaded = store.get("lesson-1")
        assert reloaded is not None
        assert reloaded.recall_count == 1

    def test_unknown_id_returns_none_does_not_raise(self, store: LessonStore) -> None:
        assert store.record_recall("no-existe") is None

    def test_reactivates_a_stale_lesson(self, store: LessonStore) -> None:
        _make_lesson(store)
        store._set_state(store.get("lesson-1"), "stale")
        assert store.get("lesson-1").state == "stale"

        updated = store.record_recall("lesson-1")
        assert updated.state == "active"


class TestApplyLifecycleTransitions:
    def test_never_used_lesson_within_grace_floor_stays_active(self, store: LessonStore) -> None:
        _make_lesson(store)  # created_at = now
        counts = store.apply_lifecycle_transitions(stale_after_days=30, archive_after_days=90)
        assert counts["marked_stale"] == 0
        assert store.get("lesson-1").state == "active"

    def test_marks_stale_after_stale_after_days_without_recall(self, store: LessonStore) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        _make_lesson(store, created_at=old)
        counts = store.apply_lifecycle_transitions(stale_after_days=30, archive_after_days=90)
        assert counts["marked_stale"] == 1
        assert store.get("lesson-1").state == "stale"

    def test_archives_after_archive_after_days_but_never_deletes_file(
        self, store: LessonStore, tmp_path: Path
    ) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        _make_lesson(store, created_at=old)
        counts = store.apply_lifecycle_transitions(stale_after_days=30, archive_after_days=90)
        assert counts["archived"] == 1
        lesson = store.get("lesson-1")
        assert lesson.state == "archived"
        # nunca borra: el fichero sigue en disco, la lección sigue accesible
        assert (tmp_path / "lessons" / "lesson-1.json").is_file()

    def test_reactivates_stale_lesson_on_renewed_real_recall(self, store: LessonStore) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        _make_lesson(store, created_at=old)
        store.apply_lifecycle_transitions(stale_after_days=30, archive_after_days=90)
        assert store.get("lesson-1").state == "stale"

        store.record_recall("lesson-1")  # uso real
        assert store.get("lesson-1").state == "active"

        # una nueva pasada, anclada en el recall reciente, no la vuelve a marcar stale
        counts = store.apply_lifecycle_transitions(stale_after_days=30, archive_after_days=90)
        assert counts["marked_stale"] == 0
        assert store.get("lesson-1").state == "active"

    def test_backward_compat_defaults_for_pre_existing_lessons(self, store: LessonStore) -> None:
        # Lecciones guardadas ANTES de este campo (sin recall_count/state en el JSON)
        # se leen con defaults limpios — mismo patrón que occurrence_count/last_seen_at.
        lesson_dict = {
            "id": "old-lesson",
            "title": "legado",
            "provenance": "internal_failure",
            "detection_heuristic": "h",
            "avoid_pattern": "p",
            "evidence": {},
        }
        reloaded = Lesson.from_dict(lesson_dict)
        assert reloaded.recall_count == 0
        assert reloaded.last_recalled_at == ""
        assert reloaded.state == "active"
