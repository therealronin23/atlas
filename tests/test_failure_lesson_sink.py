"""
FailureLessonSink: conecta fallos recurrentes del pipeline de autoauditoría a
LessonStore.record_recurring. Sin mocks de filesystem — LessonStore real
sobre tmp_path (mismo patrón que tests/test_lesson_store.py).

También verifica que LessonRecaller puede recuperar lecciones del almacén
curado (read_store) y que su recall_count se incrementa — el split
curado/runtime es deliberado (ver WORK_LEDGER / self_build_runner).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.self_maintenance.failure_lesson_sink import FailureLessonSink
from atlas.immunity.lesson_recaller import LessonRecaller
from atlas.memory.embeddings import StubEmbedder


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


_PASS_EV = {"verdict": "pass"}


def _lesson(
    lid: str,
    avoid_pattern: str,
    detection_heuristic: str,
    title: str = "t",
) -> Lesson:
    return Lesson(
        id=lid,
        title=title,
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic=detection_heuristic,
        avoid_pattern=avoid_pattern,
        evidence=_PASS_EV,
    )


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


class TestLessonRecallerMultiStore:
    """Verifica que LessonRecaller lee del almacén curado (read_store) y
    que el recall_count de la lección curada se incrementa tras un match.

    El split curado/runtime es deliberado: las lecciones curadas viven en
    <repo>/workspace/lessons (trackeadas por git); las de runtime en
    ~/atlas/memory/lessons (aprendidas en caliente). El recaller lee de
    ambos pero no copia lecciones de un store al otro.
    """

    def test_curated_lesson_recovered_via_recall(self, tmp_path: Path) -> None:
        runtime_store = LessonStore(tmp_path / "runtime")
        curated_store = LessonStore(tmp_path / "curated")
        curated_store.add(_lesson("curated-1",
            avoid_pattern="eval injection user input",
            detection_heuristic="detect eval"))

        recaller = LessonRecaller(
            runtime_store,
            embedder=StubEmbedder(dim=64),
            threshold=0.8,
            read_stores=[curated_store],
        )
        recaller.index()

        result = recaller.recall("eval injection user input")
        assert result is not None
        assert result.lesson_id == "curated-1"
        assert result.matched is True

    def test_curated_lesson_recovered_via_recall_all(self, tmp_path: Path) -> None:
        runtime_store = LessonStore(tmp_path / "runtime")
        curated_store = LessonStore(tmp_path / "curated")
        curated_store.add(_lesson("curated-1",
            avoid_pattern="eval injection user input",
            detection_heuristic="detect eval"))

        recaller = LessonRecaller(
            runtime_store,
            embedder=StubEmbedder(dim=64),
            threshold=0.8,
            read_stores=[curated_store],
        )
        recaller.index()

        results = recaller.recall_all("eval injection user input", k=5)
        ids = [r.lesson_id for r in results]
        assert "curated-1" in ids

    def test_curated_lesson_recall_count_increments(self, tmp_path: Path) -> None:
        runtime_store = LessonStore(tmp_path / "runtime")
        curated_store = LessonStore(tmp_path / "curated")
        curated_store.add(_lesson("curated-1",
            avoid_pattern="eval injection user input",
            detection_heuristic="detect eval"))

        recaller = LessonRecaller(
            runtime_store,
            embedder=StubEmbedder(dim=64),
            threshold=0.8,
            read_stores=[curated_store],
        )
        recaller.index()

        lesson_before = curated_store.get("curated-1")
        assert lesson_before is not None
        assert lesson_before.recall_count == 0

        result = recaller.recall("eval injection user input")
        assert result is not None
        assert result.matched is True

        lesson_after = curated_store.get("curated-1")
        assert lesson_after is not None
        assert lesson_after.recall_count == 1

    def test_no_files_deleted_or_moved(self, tmp_path: Path) -> None:
        """No se borra ni mueve ningún fichero de lecciones."""
        runtime_store = LessonStore(tmp_path / "runtime")
        curated_store = LessonStore(tmp_path / "curated")
        curated_store.add(_lesson("curated-1",
            avoid_pattern="eval injection",
            detection_heuristic="detect eval"))

        recaller = LessonRecaller(
            runtime_store,
            embedder=StubEmbedder(dim=64),
            threshold=0.8,
            read_stores=[curated_store],
        )
        recaller.index()
        recaller.recall("eval injection")

        # El fichero curado sigue existiendo
        assert (tmp_path / "curated" / "curated-1.json").is_file()
        # El store de runtime sigue vacío (no se copió nada)
        assert list((tmp_path / "runtime").glob("*.json")) == []
        # El store curado tiene exactamente 1 lección
        assert len(curated_store.all()) == 1
