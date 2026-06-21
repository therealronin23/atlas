"""
Tests para PatternAbstractor (Fase 1b) — ejemplos → patrones.

La UNIDAD de aprendizaje real es el PATRÓN (clase abstracta), no el ejemplo
crudo. El abstractor agrupa lecciones por similitud (clustering determinista,
sin deps) y el recall opera sobre el CENTROIDE del patrón, no sobre el string.

Lo que se prueba (criterios de aceptación de la checklist):
1. Lecciones con el mismo vocabulario colapsan en UN patrón (n_examples=N).
2. Vocabularios disjuntos → patrones distintos.
3. Determinismo: mismo corpus → mismos patrones (mismos ids estables por contenido).
4. Recall sobre patrones: una reformulación casa con el patrón correcto.
5. El centroide es la media L2-normalizada de los miembros.
6. Cada lección queda asignada a su pattern_id (lineage hacia el patrón).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.pattern_abstractor import Pattern, PatternAbstractor, PatternMatch

_PASS_EV = {"verdict": "pass"}


def _lesson(lid: str, avoid: str, heur: str = "") -> Lesson:
    return Lesson(
        id=lid,
        title="t",
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic=heur,
        avoid_pattern=avoid,
        evidence=_PASS_EV,
    )


def _store(tmp_path: Path, lessons: list[Lesson]) -> LessonStore:
    s = LessonStore(tmp_path / "lessons")
    for le in lessons:
        s.add(le)
    return s


def _abstractor() -> PatternAbstractor:
    return PatternAbstractor(embedder=StubEmbedder(dim=64), threshold=0.8)


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


class TestClustering:
    def test_empty_yields_no_patterns(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [])
        assert _abstractor().abstract(store.all()) == []

    def test_same_vocabulary_collapses_into_one_pattern(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "codigo arbitrario ejecuta eval user_input"),  # reorden
            _lesson("l3", "ejecuta eval codigo user_input arbitrario"),  # reorden
        ]
        store = _store(tmp_path, lessons)
        patterns = _abstractor().abstract(store.all())
        assert len(patterns) == 1
        assert patterns[0].n_examples == 3
        assert set(patterns[0].member_ids) == {"l1", "l2", "l3"}

    def test_disjoint_vocabularies_make_separate_patterns(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "pickle loads datos serializados no confiables remotos"),
        ]
        store = _store(tmp_path, lessons)
        patterns = _abstractor().abstract(store.all())
        assert len(patterns) == 2

    def test_every_lesson_assigned_to_some_pattern(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "codigo arbitrario ejecuta eval user_input"),
            _lesson("l3", "pickle loads datos serializados no confiables"),
        ]
        store = _store(tmp_path, lessons)
        abs = _abstractor()
        patterns = abs.abstract(store.all())
        assignment = abs.assignment()
        assert set(assignment) == {"l1", "l2", "l3"}
        all_pattern_ids = {p.id for p in patterns}
        assert set(assignment.values()) <= all_pattern_ids


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_corpus_same_pattern_ids(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "pickle loads datos serializados no confiables"),
        ]
        store = _store(tmp_path, lessons)
        ids_a = sorted(p.id for p in _abstractor().abstract(store.all()))
        ids_b = sorted(p.id for p in _abstractor().abstract(store.all()))
        assert ids_a == ids_b

    def test_pattern_id_is_content_addressed(self, tmp_path: Path) -> None:
        # El id deriva del contenido (miembros), no del orden de inserción.
        lessons = [_lesson("l1", "eval user_input ejecuta codigo arbitrario")]
        store = _store(tmp_path, lessons)
        p = _abstractor().abstract(store.all())[0]
        assert p.id.startswith("pat-")


# ---------------------------------------------------------------------------
# Centroide
# ---------------------------------------------------------------------------


class TestCentroid:
    def test_centroid_is_l2_normalized(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "codigo arbitrario ejecuta eval user_input"),
        ]
        store = _store(tmp_path, lessons)
        p = _abstractor().abstract(store.all())[0]
        norm = math.sqrt(sum(x * x for x in p.centroid))
        assert norm == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Recall sobre patrones
# ---------------------------------------------------------------------------


class TestRecallOverPatterns:
    def test_reformulation_matches_its_pattern(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "codigo arbitrario ejecuta eval user_input"),
            _lesson("l3", "pickle loads datos serializados no confiables remotos"),
        ]
        store = _store(tmp_path, lessons)
        abs = _abstractor()
        patterns = abs.abstract(store.all())

        # Reformulación trivial del cluster eval → debe casar con su patrón.
        match = abs.recall("arbitrario eval codigo user_input ejecuta")
        assert isinstance(match, PatternMatch)
        assert match.matched
        eval_pattern = next(p for p in patterns if "l1" in p.member_ids)
        assert match.pattern_id == eval_pattern.id

    def test_recall_empty_when_no_patterns(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [])
        abs = _abstractor()
        abs.abstract(store.all())
        assert abs.recall("cualquier cosa") is None

    def test_recall_all_orders_by_score(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "pickle loads datos serializados no confiables remotos"),
        ]
        store = _store(tmp_path, lessons)
        abs = _abstractor()
        abs.abstract(store.all())
        results = abs.recall_all("eval codigo arbitrario user_input ejecuta", k=5)
        assert len(results) == 2
        assert results[0].score >= results[1].score


# ---------------------------------------------------------------------------
# Etiqueta auditable
# ---------------------------------------------------------------------------


class TestSeparateThresholds:
    """cluster_threshold (agrupar) y recall_threshold (match) son independientes
    (refinamiento 1c: elimina el confound de usar un solo umbral)."""

    def test_cluster_threshold_controls_grouping(self, tmp_path: Path) -> None:
        lessons = [
            _lesson("l1", "eval user_input ejecuta codigo arbitrario"),
            _lesson("l2", "pickle loads datos serializados no confiables remotos"),
        ]
        store = _store(tmp_path, lessons)
        # Clustering muy laxo (0.0) → todo en un patrón; recall aparte.
        loose = PatternAbstractor(
            embedder=StubEmbedder(dim=64), cluster_threshold=0.0, recall_threshold=0.8
        )
        assert len(loose.abstract(store.all())) == 1
        # Clustering estricto → patrones separados.
        strict = PatternAbstractor(
            embedder=StubEmbedder(dim=64), cluster_threshold=0.99, recall_threshold=0.8
        )
        assert len(strict.abstract(store.all())) == 2

    def test_recall_threshold_controls_match_not_grouping(self, tmp_path: Path) -> None:
        lessons = [_lesson("l1", "eval user_input ejecuta codigo arbitrario")]
        store = _store(tmp_path, lessons)
        ab = PatternAbstractor(
            embedder=StubEmbedder(dim=64), cluster_threshold=0.8, recall_threshold=0.99
        )
        ab.abstract(store.all())
        # Una reformulación con score < 0.99 no debe contar como match.
        m = ab.recall("arbitrario eval codigo")
        assert m is not None
        assert m.matched == (m.score >= 0.99)

    def test_threshold_default_sets_both(self, tmp_path: Path) -> None:
        lessons = [_lesson("l1", "eval user_input ejecuta codigo arbitrario")]
        store = _store(tmp_path, lessons)
        ab = PatternAbstractor(embedder=StubEmbedder(dim=64), threshold=0.8)
        ab.abstract(store.all())
        assert ab.recall("eval user_input ejecuta codigo arbitrario") is not None


def test_pattern_label_is_a_member_avoid_text(tmp_path: Path) -> None:
    # La etiqueta es el ejemplo más cercano al centroide (representante auditable).
    lessons = [_lesson("l1", "eval user_input ejecuta codigo arbitrario")]
    store = _store(tmp_path, lessons)
    p = _abstractor().abstract(store.all())[0]
    assert p.label == "eval user_input ejecuta codigo arbitrario"
