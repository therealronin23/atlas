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
from atlas.immunity.lesson_recaller import LessonRecaller, RecallResult, _cosine_similarity
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
        assert result.score > 0.7  # escala cruda [0,1]; texto no idéntico (compuesto avoid+heuristic vs solo avoid)
        assert result.matched is True

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
# Multi-store: lectura curada + escritura runtime
# ---------------------------------------------------------------------------


class TestMultiStoreRecall:
    """El recaller lee de múltiples LessonStore (curado + runtime) pero
    record_recall escribe en el store que contiene la lección matched.

    El split curado/runtime es deliberado (ver WORK_LEDGER / self_build_runner):
    las lecciones curadas viven en <repo>/workspace/lessons (trackeadas por
    git); las de runtime en ~/atlas/memory/lessons (aprendidas en caliente).
    Unificar rutas ensuciaría el árbol git (incidente '9 YAML regenerados').
    """

    def test_recall_finds_lesson_from_curated_store(self, tmp_path: Path) -> None:
        """Una lección que SÓLO está en el read_store (curado) se recupera."""
        runtime_store = _store(tmp_path / "runtime")
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

    def test_recall_all_includes_curated_lessons(self, tmp_path: Path) -> None:
        """recall_all devuelve lecciones de ambos stores."""
        runtime_store = _store(tmp_path / "runtime")
        runtime_store.add(_lesson("runtime-1",
            avoid_pattern="sql injection drop table",
            detection_heuristic="detect sql"))

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

        results = recaller.recall_all("anything", k=10)
        ids = {r.lesson_id for r in results}
        assert "runtime-1" in ids
        assert "curated-1" in ids

    def test_recall_count_increments_for_curated_lesson(self, tmp_path: Path) -> None:
        """record_recall incrementa recall_count de la lección curada matched."""
        runtime_store = _store(tmp_path / "runtime")
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

        # Antes del recall, recall_count == 0
        lesson_before = curated_store.get("curated-1")
        assert lesson_before is not None
        assert lesson_before.recall_count == 0

        # Recall con texto que matchea la lección curada
        result = recaller.recall("eval injection user input")
        assert result is not None
        assert result.lesson_id == "curated-1"
        assert result.matched is True

        # Después del recall, recall_count == 1
        lesson_after = curated_store.get("curated-1")
        assert lesson_after is not None
        assert lesson_after.recall_count == 1

    def test_runtime_store_not_polluted_by_curated_lessons(self, tmp_path: Path) -> None:
        """Las lecciones curadas NO se copian al store de runtime."""
        runtime_store = _store(tmp_path / "runtime")
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

        # El store de runtime sigue vacío: no se ha copiado nada
        assert runtime_store.all() == []
        # El store curado tiene la lección original (no se borró ni movió)
        assert len(curated_store.all()) == 1
        assert curated_store.get("curated-1") is not None

    def test_no_read_stores_backward_compatible(self, tmp_path: Path) -> None:
        """Sin read_stores, el comportamiento es idéntico al anterior."""
        store = _store(tmp_path)
        store.add(_lesson("l1", avoid_pattern="eval injection",
                           detection_heuristic="detect eval"))
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()

        result = recaller.recall("eval injection")
        assert result is not None
        assert result.lesson_id == "l1"
        assert result.matched is True

    def test_write_store_priority_on_id_collision(self, tmp_path: Path) -> None:
        """Si un lesson_id existe en ambos stores, gana el de escritura."""
        runtime_store = _store(tmp_path / "runtime")
        runtime_store.add(_lesson("shared-id",
            avoid_pattern="runtime pattern",
            detection_heuristic="runtime heuristic"))

        curated_store = LessonStore(tmp_path / "curated")
        curated_store.add(_lesson("shared-id",
            avoid_pattern="curated pattern",
            detection_heuristic="curated heuristic"))

        recaller = LessonRecaller(
            runtime_store,
            embedder=StubEmbedder(dim=64),
            threshold=0.8,
            read_stores=[curated_store],
        )
        recaller.index()

        # El índice tiene una sola entrada para "shared-id" (la de runtime)
        assert len(recaller._index) == 1
        result = recaller.recall("runtime pattern runtime heuristic")
        assert result is not None
        assert result.lesson_id == "shared-id"
        # record_recall debe ir al store de escritura (runtime)
        lesson_rt = runtime_store.get("shared-id")
        assert lesson_rt is not None
        assert lesson_rt.recall_count == 1
        # El store curado no se modifica
        lesson_cur = curated_store.get("shared-id")
        assert lesson_cur is not None
        assert lesson_cur.recall_count == 0


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


# ---------------------------------------------------------------------------
# Tests de _cosine_similarity (wrapper [0,1] sobre la canónica)
# ---------------------------------------------------------------------------


class TestCosineSimilarityWrapper:
    """Verifica que _cosine_similarity mapea al rango [0, 1]."""

    def test_identical_vectors_returns_one(self) -> None:
        a = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors_returns_zero(self) -> None:
        # Vectores ortogonales: raw=0 → max(0, 0) = 0.0
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors_returns_zero(self) -> None:
        # Vectores opuestos: raw=-1 → (−1+1)/2 = 0
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_result_always_in_zero_one_range(self) -> None:
        import random
        rng = random.Random(42)
        for _ in range(50):
            a = [rng.uniform(-1, 1) for _ in range(8)]
            b = [rng.uniform(-1, 1) for _ in range(8)]
            score = _cosine_similarity(a, b)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# La telemetría del camino caliente: `recall_all` no contaba nada
# ---------------------------------------------------------------------------
#
# Medido el 2026-08-10 y es peor que un contador ciego. `recall()` registra el
# uso (`record_recall` → `recall_count`, `last_recalled_at`); `recall_all()` NO
# registraba nada, nunca. Y el único consumidor del camino caliente
# —`_build_avoid_section`, que usan ToolCoder y AtlasCoder para meter los
# patrones a evitar en el prompt de codegen— llama a `recall_all`.
#
# Consecuencia comprobada: 17 lecciones curadas con `recall_count` total = 1,
# mientras 3 de 4 tareas realistas SÍ recuperaban patrones. La conclusión obvia
# ("el subsistema de lecciones está dormido") era falsa; lo que estaba roto era
# la medición.
#
# Y no es sólo una métrica ciega: `apply_lifecycle_transitions` se ancla en
# `last_recalled_at` para pasar active→stale a los 30 días y →archived a los 90.
# Sin registrar el uso real, **el sistema marca como obsoletas justo las
# lecciones que está usando**. Explica el "16 de 17 en stale" de la auditoría.
#
# `recall_all` nació como herramienta de ANÁLISIS ("trazar la curva de
# similitud"), y trazar una curva no debe reactivar lecciones. Por eso el
# registro es opt-in explícito en la llamada, no un efecto secundario nuevo.


class TestTelemetriaDeRecallAll:
    def _con_leccion(self, tmp_path: Path) -> tuple[LessonRecaller, LessonStore, str]:
        store = _store(tmp_path)
        store.add(_lesson("l1", "no uses shell=True", "subprocess con shell=True"))
        rec = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        rec.index()
        return rec, store, "subprocess con shell=True"

    def test_por_defecto_analizar_no_deja_rastro(self, tmp_path: Path) -> None:
        """Trazar la curva de similitud no puede reactivar una lección."""
        rec, store, consulta = self._con_leccion(tmp_path)

        rec.recall_all(consulta, k=3)

        assert store.get("l1").recall_count == 0
        assert not store.get("l1").last_recalled_at

    def test_el_camino_caliente_sí_cuenta_el_uso(self, tmp_path: Path) -> None:
        rec, store, consulta = self._con_leccion(tmp_path)

        resultados = rec.recall_all(consulta, k=3, record=True)

        assert any(r.matched for r in resultados), "el stub no hizo match: test inútil"
        assert store.get("l1").recall_count == 1
        assert store.get("l1").last_recalled_at is not None

    def test_solo_cuenta_las_que_realmente_hacen_match(self, tmp_path: Path) -> None:
        """Los top-k incluyen no-matches por debajo del umbral. Contarlos
        inflaría el uso y mantendría vivas lecciones que nadie aplica."""
        store = _store(tmp_path)
        store.add(_lesson("l1", "no uses shell=True", "subprocess con shell=True"))
        store.add(_lesson("l2", "otra cosa", "vocabulario totalmente distinto aqui"))
        rec = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        rec.index()

        rec.recall_all("subprocess con shell=True", k=5, record=True)

        assert store.get("l1").recall_count == 1
        assert store.get("l2").recall_count == 0

    def test_el_prompt_de_codegen_cuenta_el_uso(self, tmp_path: Path) -> None:
        """La prueba que cierra el círculo: por el camino REAL de producción."""
        from atlas.core.orchestrator_parts.maintenance_facade import _build_avoid_section

        rec, store, consulta = self._con_leccion(tmp_path)

        seccion = _build_avoid_section(rec, store, consulta)

        assert "no uses shell=True" in seccion
        assert store.get("l1").recall_count == 1, (
            "la lección se sirvió al prompt y el uso no se registró"
        )
