"""
Tests para SqliteLessonIndex — índice persistente derivado del LessonStore (Fase 1a).

Lo que se prueba (criterios de aceptación de la checklist en
docs/design/design_verifiable_memory.md):

1. PARIDAD: para el mismo corpus + mismo embedder + mismo threshold, los scores
   de recall/recall_all son IDÉNTICOS a los del LessonRecaller in-memory. El
   índice SQLite no cambia la matemática (coseno), solo la persiste.
2. PERSISTENCIA: el índice sobrevive a cerrar y reabrir el fichero — no hay que
   re-embeber al arrancar (eso es el valor de 1a, no la velocidad).
3. RECONSTRUIBILIDAD: el índice es una vista derivada; `rebuild_from(store)` lo
   reconstruye desde cero (el CORE = LessonStore/Merkle es la fuente de verdad).
4. ENLACE MERKLE: cada fila puede llevar merkle_leaf_hash (cimiento moat-1);
   nullable mientras no se aporte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.immunity.lesson_recaller import LessonRecaller, RecallResult
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.lesson_index import SqliteLessonIndex

_PASS_EV = {"verdict": "pass"}


def _lesson(lid: str, avoid: str, heur: str, title: str = "t") -> Lesson:
    return Lesson(
        id=lid,
        title=title,
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic=heur,
        avoid_pattern=avoid,
        evidence=_PASS_EV,
    )


def _seeded_store(tmp_path: Path) -> LessonStore:
    store = LessonStore(tmp_path / "lessons")
    store.add(_lesson("l1", "eval(user_input) ejecuta código arbitrario", "busca eval con input"))
    store.add(_lesson("l2", "os.system con cadena sin sanear", "busca os.system shell"))
    store.add(_lesson("l3", "pickle.loads de datos no confiables", "busca pickle loads remoto"))
    return store


def _index(tmp_path: Path, store: LessonStore) -> SqliteLessonIndex:
    idx = SqliteLessonIndex(
        tmp_path / "index.db",
        embedder=StubEmbedder(dim=64),
        threshold=0.8,
    )
    idx.rebuild_from(store)
    return idx


# ---------------------------------------------------------------------------
# Paridad con LessonRecaller
# ---------------------------------------------------------------------------


class TestParity:
    @pytest.mark.parametrize(
        "query",
        [
            "eval(user_input) ejecuta código arbitrario",   # idéntico a l1
            "código arbitrario ejecuta eval con user_input",  # reorden léxico
            "os.system cadena sin sanear shell",
            "algo totalmente distinto sin solapamiento",
            "",  # vacío
        ],
    )
    def test_recall_scores_match_in_memory(self, tmp_path: Path, query: str) -> None:
        store = _seeded_store(tmp_path)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()
        idx = _index(tmp_path, store)

        ref = recaller.recall(query)
        got = idx.recall(query)

        if ref is None:
            assert got is None
        else:
            assert got is not None
            assert got.lesson_id == ref.lesson_id
            assert got.score == pytest.approx(ref.score)
            assert got.matched == ref.matched

    def test_recall_all_scores_match_in_memory(self, tmp_path: Path) -> None:
        store = _seeded_store(tmp_path)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        recaller.index()
        idx = _index(tmp_path, store)

        query = "os.system cadena sin sanear shell"
        ref = recaller.recall_all(query, k=5)
        got = idx.recall_all(query, k=5)

        assert [r.lesson_id for r in got] == [r.lesson_id for r in ref]
        for g, r in zip(got, ref):
            assert g.score == pytest.approx(r.score)
            assert g.matched == r.matched


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_survives_reopen_without_rebuild(self, tmp_path: Path) -> None:
        store = _seeded_store(tmp_path)
        db = tmp_path / "index.db"
        idx = SqliteLessonIndex(db, embedder=StubEmbedder(dim=64), threshold=0.8)
        idx.rebuild_from(store)
        first = idx.recall("eval(user_input) ejecuta código arbitrario")
        idx.close()

        # Reabrir SIN rebuild: el índice persistió en disco.
        reopened = SqliteLessonIndex(db, embedder=StubEmbedder(dim=64), threshold=0.8)
        assert reopened.count() == 3
        again = reopened.recall("eval(user_input) ejecuta código arbitrario")
        assert again is not None and first is not None
        assert again.lesson_id == first.lesson_id
        assert again.score == pytest.approx(first.score)


# ---------------------------------------------------------------------------
# Reconstruibilidad + enlace Merkle
# ---------------------------------------------------------------------------


class TestRebuildAndProvenance:
    def test_rebuild_is_idempotent(self, tmp_path: Path) -> None:
        store = _seeded_store(tmp_path)
        idx = _index(tmp_path, store)
        before = idx.recall_all("pickle.loads de datos no confiables")
        idx.rebuild_from(store)  # otra vez
        after = idx.recall_all("pickle.loads de datos no confiables")
        assert idx.count() == 3
        assert [r.lesson_id for r in before] == [r.lesson_id for r in after]

    def test_merkle_leaf_hash_persisted_when_present(self, tmp_path: Path) -> None:
        store = LessonStore(tmp_path / "lessons")
        store.add(_lesson("l1", "eval(user_input)", "busca eval"))
        idx = SqliteLessonIndex(tmp_path / "index.db", embedder=StubEmbedder(dim=64))
        idx.upsert(
            store.get("l1"),  # type: ignore[arg-type]
            merkle_leaf_hash="deadbeef",
            merkle_leaf_index=7,
        )
        assert idx.merkle_leaf_hash("l1") == "deadbeef"
        assert idx.merkle_leaf_index("l1") == 7

    def test_empty_store_yields_no_results(self, tmp_path: Path) -> None:
        store = LessonStore(tmp_path / "lessons")
        idx = _index(tmp_path, store)
        assert idx.count() == 0
        assert idx.recall("cualquier cosa") is None
        assert idx.recall_all("cualquier cosa") == []


# ---------------------------------------------------------------------------
# Tipo de retorno
# ---------------------------------------------------------------------------


def test_returns_recall_result_type(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    idx = _index(tmp_path, store)
    res = idx.recall("eval(user_input) ejecuta código arbitrario")
    assert isinstance(res, RecallResult)


# ---------------------------------------------------------------------------
# CABLEADO: SqliteLessonIndex como drop-in del LessonRecaller en TeacherDebate
# ---------------------------------------------------------------------------


class TestCablingIntoTeacherDebate:
    """1a cableado: el TeacherDebate consume el índice PERSISTENTE vía el
    protocolo `Recaller`, no el escaneo in-memory. Mismas decisiones."""

    def test_satisfies_recaller_protocol(self, tmp_path: Path) -> None:
        from atlas.immunity.lesson_recaller import Recaller

        store = _seeded_store(tmp_path)
        idx = SqliteLessonIndex(
            tmp_path / "index.db", embedder=StubEmbedder(dim=64), store=store
        )
        assert isinstance(idx, Recaller)

    def test_index_alias_rebuilds_from_store(self, tmp_path: Path) -> None:
        store = LessonStore(tmp_path / "lessons")
        idx = SqliteLessonIndex(
            tmp_path / "index.db", embedder=StubEmbedder(dim=64), store=store
        )
        idx.index()
        assert idx.count() == 0
        store.add(_lesson("l1", "eval(user_input) ejecuta código arbitrario", "busca eval"))
        idx.index()  # captura lecciones añadidas en sesión (igual que LessonRecaller)
        assert idx.count() == 1

    def test_index_without_store_raises(self, tmp_path: Path) -> None:
        idx = SqliteLessonIndex(tmp_path / "index.db", embedder=StubEmbedder(dim=64))
        with pytest.raises(RuntimeError, match="requiere construir con store"):
            idx.index()

    def test_teacher_debate_corroborates_prior_via_sqlite_index(self, tmp_path: Path) -> None:
        from atlas.immunity.teacher_debate import (
            DebateOutcome,
            LessonProposal,
            TeacherDebate,
        )

        store = LessonStore(tmp_path / "lessons")
        store.add(
            Lesson(
                id="l1",
                title="t",
                provenance=LessonProvenance.INTERNAL_FAILURE,
                detection_heuristic="busca eval con input",
                avoid_pattern="eval(user_input) ejecuta código arbitrario",
                evidence=_PASS_EV,
                tags=("stance:avoid",),
            )
        )
        idx = SqliteLessonIndex(
            tmp_path / "index.db", embedder=StubEmbedder(dim=64), threshold=0.8, store=store
        )
        debate = TeacherDebate(store, idx)

        # Propuesta con el mismo vocabulario → casa con el prior → CORROBORATED.
        proposal = LessonProposal(
            detection_heuristic="busca eval con input",
            avoid_pattern="código arbitrario eval(user_input) ejecuta",
            stance="avoid",
            rationale="reformulación trivial",
            teacher_id="test",
        )
        result = debate.consider(proposal)
        assert result.outcome is DebateOutcome.CORROBORATED
        assert result.matched_lesson_id == "l1"

    def test_teacher_debate_accepts_novel_via_sqlite_index(self, tmp_path: Path) -> None:
        from atlas.immunity.teacher_debate import DebateOutcome, LessonProposal, TeacherDebate

        store = LessonStore(tmp_path / "lessons")
        idx = SqliteLessonIndex(
            tmp_path / "index.db", embedder=StubEmbedder(dim=64), threshold=0.8, store=store
        )
        debate = TeacherDebate(store, idx)

        proposal = LessonProposal(
            detection_heuristic="busca pickle loads remoto",
            avoid_pattern="pickle.loads de datos no confiables",
            stance="avoid",
            rationale="novel y verificable",
            teacher_id="test",
        )
        result = debate.consider(proposal)
        assert result.outcome is DebateOutcome.ACCEPTED_NEW
        # La lección novel quedó persistida en el store (CORE) y, al reindexar,
        # también en el índice SQLite.
        assert store.get(result.lesson_id) is not None
        idx.index()
        assert idx.count() == 1
