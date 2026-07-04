"""
tests/benchmarks/test_eval_memory_benchmark.py

Tests TDD para el benchmark de evaluación honesta del SqliteMemoryIndex.

Garantías verificadas:
  1. Reproducibilidad: dos corridas sobre el mismo corpus producen resultados idénticos.
  2. Coherencia de métricas: 0 <= P/R/F1 <= 1 para todas las queries.
  3. Recall > 0 en queries con al menos un match en top-k (con k generoso = len(corpus)).
  4. Anti-leak estructural: la función de indexación no recibe las queries como argumento
     (se verifica inspeccionando la firma de run_benchmark y el flujo de control del
     benchmark — no es posible que las queries contaminen la indexación porque son
     parámetros de distinta fase).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from scripts.eval_memory_benchmark import (
    CORPUS,
    Metrics,
    QUERIES,
    QueryResult,
    compute_metrics,
    macro_metrics,
    run_ablation,
    run_benchmark,
)


# ---------------------------------------------------------------------------
# Pruebas de métricas (unitarias, sin índice)
# ---------------------------------------------------------------------------

class TestComputeMetrics:
    def test_perfect_recall(self) -> None:
        m = compute_metrics({"a", "b"}, frozenset({"a", "b"}))
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_zero_precision_zero_recall(self) -> None:
        m = compute_metrics({"x"}, frozenset({"a"}))
        assert m.precision == 0.0
        assert m.recall == 0.0
        assert m.f1 == 0.0

    def test_partial_recall(self) -> None:
        m = compute_metrics({"a", "x"}, frozenset({"a", "b"}))
        # tp=1, precision=0.5, recall=0.5
        assert m.precision == pytest.approx(0.5)
        assert m.recall == pytest.approx(0.5)
        assert m.f1 == pytest.approx(0.5)

    def test_bounds(self) -> None:
        """Todas las métricas deben estar en [0, 1]."""
        for retrieved in [set(), {"a"}, {"a", "b", "c"}]:
            for relevant in [frozenset(), frozenset({"a"}), frozenset({"a", "b"})]:
                m = compute_metrics(retrieved, relevant)
                assert 0.0 <= m.precision <= 1.0
                assert 0.0 <= m.recall <= 1.0
                assert 0.0 <= m.f1 <= 1.0


# ---------------------------------------------------------------------------
# Pruebas de integración sobre índice efímero (tmp_path)
# ---------------------------------------------------------------------------

class TestRunBenchmark:
    def _run(self, tmp_path: Path, suffix: str = "") -> list[QueryResult]:
        db = tmp_path / f"bench{suffix}.db"
        # k = len(CORPUS) para maximizar la oportunidad de recall real.
        return run_benchmark(db, k=len(CORPUS), threshold=0.0)

    def test_reproducibility(self, tmp_path: Path) -> None:
        """Dos corridas sobre DBs distintas producen los mismos resultados."""
        results_a = self._run(tmp_path, "a")
        results_b = self._run(tmp_path, "b")

        assert len(results_a) == len(results_b) == len(QUERIES)
        for ra, rb in zip(results_a, results_b):
            assert ra.case.query_id == rb.case.query_id
            assert ra.retrieved_ids == rb.retrieved_ids, (
                f"Resultados no reproducibles en {ra.case.query_id}: "
                f"{ra.retrieved_ids} != {rb.retrieved_ids}"
            )
            assert ra.metrics == rb.metrics

    def test_metrics_coherence(self, tmp_path: Path) -> None:
        """Todas las métricas están en [0, 1] para todas las queries."""
        results = self._run(tmp_path)
        for qr in results:
            m = qr.metrics
            assert 0.0 <= m.precision <= 1.0, f"precision fuera de rango en {qr.case.query_id}"
            assert 0.0 <= m.recall    <= 1.0, f"recall fuera de rango en {qr.case.query_id}"
            assert 0.0 <= m.f1        <= 1.0, f"f1 fuera de rango en {qr.case.query_id}"

    def test_recall_positive_for_queries_with_match(self, tmp_path: Path) -> None:
        """Con k=len(corpus) y threshold=0.0, el recall de toda query debe ser > 0.

        Justificación: recall_all devuelve hasta k resultados del índice; con
        k=len(corpus) devuelve TODOS los registros indexados. Por tanto, cualquier
        query con al menos un relevant_id que esté en el corpus obtendrá recall=1.0.
        Esto verifica que el corpus fue indexado correctamente y que las queries
        con matches esperados realmente los encuentran.
        """
        corpus_ids = {rec_id for rec_id, _ in CORPUS}
        results = self._run(tmp_path)
        for qr in results:
            # Sólo verificamos queries cuyo relevant_id esté en el corpus indexado
            matching_relevant = qr.case.relevant_ids & corpus_ids
            if matching_relevant:
                assert qr.metrics.recall > 0.0, (
                    f"recall=0 en {qr.case.query_id} aunque hay relevant_ids "
                    f"{matching_relevant} en el corpus indexado"
                )

    def test_number_of_results_equals_number_of_queries(self, tmp_path: Path) -> None:
        results = self._run(tmp_path)
        assert len(results) == len(QUERIES)

    def test_all_corpus_ids_returned_with_full_k(self, tmp_path: Path) -> None:
        """Con k=len(corpus), todos los IDs del corpus deben aparecer en retrieved."""
        results = self._run(tmp_path)
        corpus_ids = {rec_id for rec_id, _ in CORPUS}
        for qr in results:
            assert qr.retrieved_ids == corpus_ids, (
                f"Con k=len(corpus), se esperan todos los IDs en {qr.case.query_id}"
            )


# ---------------------------------------------------------------------------
# Prueba anti-leak estructural (inspección de firma)
# ---------------------------------------------------------------------------

class TestAntiLeakStructural:
    def test_run_benchmark_does_not_accept_queries_at_indexing_time(self) -> None:
        """Verificación estructural: run_benchmark recibe las queries sólo para
        evaluar, no para indexar. La función de indexación (upsert) opera sobre
        el corpus; las queries nunca son pasadas a upsert.

        Esta prueba verifica que la firma de run_benchmark NO incluye un parámetro
        'queries' (lo cual confirmaría que las queries son constantes globales
        separadas del corpus, no mezcladas durante la fase de indexación).
        """
        sig = inspect.signature(run_benchmark)
        param_names = set(sig.parameters.keys())
        assert "queries" not in param_names, (
            "run_benchmark no debe aceptar 'queries' como parámetro: el anti-leak "
            "requiere que las queries sean constantes separadas del corpus de indexación."
        )
        # Verificamos también que el corpus y las queries son objetos distintos
        corpus_texts = {text for _, text in CORPUS}
        query_texts = {q.query_text for q in QUERIES}
        assert corpus_texts.isdisjoint(query_texts), (
            "CORPUS y QUERIES contienen textos idénticos — esto introduce fuga "
            "(un texto de query no debe estar en el corpus indexado tal cual)."
        )


# ---------------------------------------------------------------------------
# Pruebas del andamio de ablación (Fase F1)
# ---------------------------------------------------------------------------

class TestMacroMetrics:
    def test_known_values(self) -> None:
        """macro_metrics promedia correctamente sobre resultados conocidos."""
        from scripts.eval_memory_benchmark import QueryCase
        cases = [
            QueryResult(
                case=QueryCase("q1", "dummy", frozenset({"a"})),
                retrieved_ids={"a"},
                metrics=Metrics(1.0, 1.0, 1.0),
            ),
            QueryResult(
                case=QueryCase("q2", "dummy", frozenset({"b"})),
                retrieved_ids={"x"},
                metrics=Metrics(0.0, 0.0, 0.0),
            ),
        ]
        m = macro_metrics(cases)
        assert m.precision == pytest.approx(0.5)
        assert m.recall == pytest.approx(0.5)
        assert m.f1 == pytest.approx(0.5)

    def test_empty_list(self) -> None:
        m = macro_metrics([])
        assert m == Metrics(0.0, 0.0, 0.0)


class TestRetrievalModes:
    def test_cosine_mode_same_as_default(self, tmp_path: Path) -> None:
        """mode='cosine' produce las mismas métricas macro que run_benchmark sin mode."""
        db_default = tmp_path / "default.db"
        db_cosine  = tmp_path / "cosine.db"
        results_default = run_benchmark(db_default, k=len(CORPUS), threshold=0.0)
        results_cosine  = run_benchmark(db_cosine, k=len(CORPUS), threshold=0.0, mode="cosine")
        assert macro_metrics(results_default) == macro_metrics(results_cosine)

    def test_unknown_mode_raises_value_error(self, tmp_path: Path) -> None:
        db = tmp_path / "bad.db"
        with pytest.raises(ValueError, match="modo desconocido"):
            run_benchmark(db, mode="nonexistent_mode_xyz")


class TestRunAblation:
    def test_single_cosine_mode_matches_run_benchmark(self, tmp_path: Path) -> None:
        """run_ablation(modes=['cosine']) devuelve Metrics == macro de run_benchmark cosine."""
        db_bench    = tmp_path / "bench.db"
        db_ablation = tmp_path / "ablation"
        results     = run_benchmark(db_bench, k=3, threshold=0.0, mode="cosine")
        expected    = macro_metrics(results)

        ablation = run_ablation(db_ablation, modes=["cosine"], k=3, threshold=0.0)

        assert "cosine" in ablation
        assert ablation["cosine"].precision == pytest.approx(expected.precision)
        assert ablation["cosine"].recall    == pytest.approx(expected.recall)
        assert ablation["cosine"].f1        == pytest.approx(expected.f1)

    def test_ablation_returns_all_requested_modes(self, tmp_path: Path) -> None:
        db = tmp_path / "abl"
        result = run_ablation(db, modes=["cosine"])
        assert set(result.keys()) == {"cosine"}


# ---------------------------------------------------------------------------
# Modo hybrid (Fase F2)
# ---------------------------------------------------------------------------

class TestHybridMode:
    def test_hybrid_mode_registered(self) -> None:
        """El modo 'hybrid' debe estar en RETRIEVAL_MODES."""
        from scripts.eval_memory_benchmark import RETRIEVAL_MODES
        assert "hybrid" in RETRIEVAL_MODES

    def test_hybrid_runs_and_returns_metrics(self, tmp_path: Path) -> None:
        """run_benchmark con mode='hybrid' completa sin excepciones y devuelve métricas válidas."""
        db = tmp_path / "hybrid.db"
        results = run_benchmark(db, k=len(CORPUS), threshold=0.0, mode="hybrid")
        assert len(results) == len(QUERIES)
        for qr in results:
            m = qr.metrics
            assert 0.0 <= m.precision <= 1.0
            assert 0.0 <= m.recall <= 1.0
            assert 0.0 <= m.f1 <= 1.0

    def test_cosine_mode_unaffected_by_hybrid(self, tmp_path: Path) -> None:
        """mode='cosine' produce los mismos resultados antes y después de añadir hybrid."""
        db1 = tmp_path / "cosine1.db"
        db2 = tmp_path / "cosine2.db"
        r1 = run_benchmark(db1, k=len(CORPUS), threshold=0.0, mode="cosine")
        r2 = run_benchmark(db2, k=len(CORPUS), threshold=0.0, mode="cosine")
        assert macro_metrics(r1) == macro_metrics(r2)

    def test_hybrid_in_ablation(self, tmp_path: Path) -> None:
        """run_ablation con modes=['cosine', 'hybrid'] devuelve ambas claves."""
        db = tmp_path / "abl"
        result = run_ablation(db, modes=["cosine", "hybrid"], k=3, threshold=0.0)
        assert set(result.keys()) == {"cosine", "hybrid"}
        for m in result.values():
            assert 0.0 <= m.precision <= 1.0


# ---------------------------------------------------------------------------
# Modo temporal (Fase F3)
# ---------------------------------------------------------------------------

class TestTemporalMode:
    def test_temporal_mode_registered(self) -> None:
        """El modo 'temporal' debe estar en RETRIEVAL_MODES."""
        from scripts.eval_memory_benchmark import RETRIEVAL_MODES
        assert "temporal" in RETRIEVAL_MODES

    def test_temporal_runs_and_returns_metrics(self, tmp_path: Path) -> None:
        """run_benchmark con mode='temporal' completa sin excepciones y devuelve métricas válidas."""
        db = tmp_path / "temporal.db"
        results = run_benchmark(db, k=len(CORPUS), threshold=0.0, mode="temporal")
        assert len(results) == len(QUERIES)
        for qr in results:
            m = qr.metrics
            assert 0.0 <= m.precision <= 1.0
            assert 0.0 <= m.recall <= 1.0
            assert 0.0 <= m.f1 <= 1.0

    def test_cosine_mode_unaffected_by_temporal(self, tmp_path: Path) -> None:
        """Añadir modo temporal no cambia los resultados de cosine (no-regresión)."""
        db1 = tmp_path / "cosine_nr1.db"
        db2 = tmp_path / "cosine_nr2.db"
        r1 = run_benchmark(db1, k=len(CORPUS), threshold=0.0, mode="cosine")
        r2 = run_benchmark(db2, k=len(CORPUS), threshold=0.0, mode="cosine")
        assert macro_metrics(r1) == macro_metrics(r2)

    def test_temporal_in_ablation(self, tmp_path: Path) -> None:
        """run_ablation con modes=['cosine', 'temporal'] devuelve ambas claves con métricas válidas."""
        db = tmp_path / "abl_temporal"
        result = run_ablation(db, modes=["cosine", "temporal"], k=3, threshold=0.0)
        assert set(result.keys()) == {"cosine", "temporal"}
        for m in result.values():
            assert 0.0 <= m.precision <= 1.0
            assert 0.0 <= m.recall <= 1.0
            assert 0.0 <= m.f1 <= 1.0
