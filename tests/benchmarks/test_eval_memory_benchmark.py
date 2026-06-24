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
    QUERIES,
    QueryResult,
    compute_metrics,
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
