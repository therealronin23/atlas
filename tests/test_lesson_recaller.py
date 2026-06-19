"""
Tests para LessonRecaller — near-duplicate detection sobre LessonStore.

NOTA StubEmbedder: la similitud es léxica-ish (hash de tokens SHA-256).
Dos textos con vocabulario idéntico → score ~1.0.
Paráfrasis semánticas con vocabulario distinto → score bajo (limitación
esperada; la semántica real requiere LiteLLMEmbedder, que es inyectable).
Los tests de "reformulación" usan solapamiento léxico real (mismas palabras,
distinto orden) para que StubEmbedder dé similitud alta.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.immunity.lesson_recaller import LessonRecaller, RecallResult
from atlas.memory.embeddings import StubEmbedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS_EV = {"verdict": "pass"}


def _store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


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


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def recaller(tmp_path: Path) -> LessonRecaller:
    store = _store(tmp_path)
    return LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)


# ---------------------------------------------------------------------------
# Store vacío
# ---------------------------------------------------------------------------


class TestEmptyStore:
    def test_recall_returns_none(self, recaller: LessonRecaller) -> None:
        recaller.index()
        assert recaller.recall("eval(user_input)") is None

    def test_recall_all_returns_empty(self, recaller: LessonRecaller) -> None:
        recaller.index()
        assert recaller.recall_all("eval(user_input)") == []


# ---------------------------------------------------------------------------
# Recall exacto
# ---------------------------------------------------------------------------


class TestExactRecall:
    def test_exact_match_score_near_one(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        avoid = "eval user_input injection"
        lesson = store.add(_lesson("l1", avoid_pattern=avoid, detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        result = recaller.recall(avoid)

        assert result is not None
        assert result.lesson_id == lesson.id
        # Texto idéntico → similitud coseno de la representación muy alta.
        # Con StubEmbedder el vector de un texto vs sí mismo es 1.0, pero el
        # texto de la lección combina avoid_pattern + detection_heuristic, así
        # que hacemos el mismo match contra ese texto compuesto.
        assert result.score > 0.9

    def test_exact_match_on_full_lesson_text(self, tmp_path: Path) -> None:
        """Recall con el texto exacto que usa el recaller internamente."""
        store = _store(tmp_path)
        lesson = store.add(_lesson("l1",
            avoid_pattern="eval injection",
            detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        # Texto que combina ambos campos — máxima similitud esperada
        full_text = "eval injection detect eval"
        result = recaller.recall(full_text)

        assert result is not None
        assert result.lesson_id == lesson.id
        assert result.matched is True
        assert result.score >= 0.8


# ---------------------------------------------------------------------------
# Recall reformulación (solapamiento léxico)
# ---------------------------------------------------------------------------


class TestReformulationRecall:
    """
    Con StubEmbedder la similitud es léxica-ish: mismas palabras, distinto
    orden → slots de hash similares → score alto.
    Paráfrasis semánticas reales (sin solapamiento léxico) NO darán score
    alto; para eso se necesita LiteLLMEmbedder (inyectable).
    """

    def test_reordered_tokens_give_high_score(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        avoid = "eval injection user input bypass"
        lesson = store.add(_lesson("l1", avoid_pattern=avoid,
                                   detection_heuristic="detect eval bypass"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.6)
        recaller.index()

        # Mismas palabras del avoid_pattern, distinto orden
        variant = "bypass user input injection eval"
        result = recaller.recall(variant)

        assert result is not None
        assert result.lesson_id == lesson.id
        # StubEmbedder: mismos tokens → mismos slots → similitud alta
        assert result.score >= 0.6, (
            f"score={result.score:.3f} — con StubEmbedder el solapamiento léxico "
            "debe dar similitud alta. Si falla aquí el StubEmbedder cambió de impl."
        )


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------


class TestNoMatch:
    def test_unrelated_text_gives_low_score(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval user input injection",
                           detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        result = recaller.recall("completely different unrelated zebra topic")

        assert result is not None
        assert result.matched is False
        assert result.score < 0.8


# ---------------------------------------------------------------------------
# Attack text vacío
# ---------------------------------------------------------------------------


class TestEmptyAttackText:
    def test_empty_text_does_not_raise(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval", detection_heuristic="h"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        result = recaller.recall("")

        assert result is not None
        assert result.score == 0.0
        assert result.matched is False

    def test_whitespace_text_does_not_raise(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval", detection_heuristic="h"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        result = recaller.recall("   ")

        assert result is not None
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# recall_all top-k
# ---------------------------------------------------------------------------


class TestRecallAll:
    def _seed(self, store: LessonStore) -> None:
        store.add(_lesson("l1", avoid_pattern="eval injection user",
                           detection_heuristic="detect eval"))
        store.add(_lesson("l2", avoid_pattern="sql injection drop table",
                           detection_heuristic="detect sql"))
        store.add(_lesson("l3", avoid_pattern="path traversal dotdot",
                           detection_heuristic="detect traversal"))

    def test_returns_k_results(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        self._seed(store)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        results = recaller.recall_all("eval injection", k=2)

        assert len(results) == 2

    def test_ordered_by_score_desc(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        self._seed(store)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        results = recaller.recall_all("eval injection user", k=3)

        assert len(results) == 3
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), (
            f"Esperado orden desc, got {scores}"
        )

    def test_returns_all_when_k_greater_than_store(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        self._seed(store)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        results = recaller.recall_all("anything", k=100)

        assert len(results) == 3  # store tiene 3 lecciones

    def test_empty_store_returns_empty_list(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        assert recaller.recall_all("eval", k=5) == []


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_result(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval injection",
                           detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        r1 = recaller.recall("eval injection attack")
        r2 = recaller.recall("eval injection attack")

        assert r1 == r2

    def test_index_idempotent(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval", detection_heuristic="h"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)

        recaller.index()
        r1 = recaller.recall("eval")
        recaller.index()  # segundo index — debe dar mismo resultado
        r2 = recaller.recall("eval")

        assert r1 == r2


# ---------------------------------------------------------------------------
# Lecciones añadidas post-index (documentación del comportamiento)
# ---------------------------------------------------------------------------


class TestPostIndexBehavior:
    def test_lesson_added_after_index_not_visible_until_reindex(
        self, tmp_path: Path
    ) -> None:
        """
        Documenta explícitamente: lecciones añadidas al store después de
        index() no aparecen en recall() hasta que se llama index() de nuevo.
        """
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval", detection_heuristic="h"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        # Añadimos segunda lección SIN reindexar
        store.add(_lesson("l2", avoid_pattern="sql injection",
                           detection_heuristic="detect sql"))

        results = recaller.recall_all("sql injection", k=10)
        ids = [r.lesson_id for r in results]
        assert "l2" not in ids, (
            "l2 no debe aparecer antes de re-index(); este test documenta la limitación"
        )

        # Tras reindexar sí aparece
        recaller.index()
        results_after = recaller.recall_all("sql injection", k=10)
        ids_after = [r.lesson_id for r in results_after]
        assert "l2" in ids_after


# ---------------------------------------------------------------------------
# RecallResult es frozen dataclass
# ---------------------------------------------------------------------------


class TestRecallResult:
    def test_frozen(self) -> None:
        r = RecallResult(lesson_id="x", score=0.9, matched=True)
        with pytest.raises((AttributeError, TypeError)):
            r.score = 0.5  # type: ignore[misc]

    def test_matched_reflects_threshold(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval injection",
                           detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.99)
        recaller.index()

        result = recaller.recall("completely unrelated text")

        assert result is not None
        # Con threshold=0.99 y texto no relacionado, matched debe ser False
        assert result.matched is False
