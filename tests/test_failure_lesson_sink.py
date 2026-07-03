"""
FailureLessonSink: conecta fallos recurrentes del pipeline de autoauditoría a
LessonStore.record_recurring. Sin mocks de filesystem — LessonStore real
sobre tmp_path (mismo patrón que tests/test_lesson_store.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import LessonStore
from atlas.core.self_maintenance.failure_lesson_sink import FailureLessonSink


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


class TestFailureLessonSink:
    def test_same_intent_and_reason_bumps_occurrence_count(self, store: LessonStore) -> None:
        sink = FailureLessonSink(store=store)
        first = sink.record(intent="aplicar patch X", reason="rompe la suite combinada (pytest_exit=1)")
        second = sink.record(intent="aplicar patch X", reason="rompe la suite combinada (pytest_exit=1)")

        assert first.id == second.id
        assert second.occurrence_count == 2
        assert len(store.all()) == 1

    def test_same_intent_different_reason_creates_separate_lesson(self, store: LessonStore) -> None:
        sink = FailureLessonSink(store=store)
        first = sink.record(intent="aplicar patch X", reason="rompe la suite combinada (pytest_exit=1)")
        second = sink.record(intent="aplicar patch X", reason="timeout en worktree")

        assert first.id != second.id
        assert len(store.all()) == 2

    def test_dedup_key_is_deterministic(self, store: LessonStore) -> None:
        sink = FailureLessonSink(store=store)
        first = sink.record(intent="aplicar patch Y", reason="motivo Z")
        second = sink.record(intent="aplicar patch Y", reason="motivo Z")
        # Determinismo verificado indirectamente: misma intent+reason siempre
        # colapsa en la MISMA lección (mismo id), nunca en una distinta.
        assert first.id == second.id
        assert "dedup:" in "".join(second.tags)
