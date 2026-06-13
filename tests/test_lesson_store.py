"""
Capa 4 — LessonStore. Todo con datos en tmp y prove-it/corroboración
capturados como input: sin red, sin subprocesos reales, sin GUI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.lesson_store import (
    Lesson,
    LessonProvenance,
    LessonPromoter,
    LessonRejected,
    LessonStore,
    LessonVerifier,
    ProveItResult,
)
from atlas.core.verify import Verdict
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


def _prove_it(failed_before: bool = True, passes_after: bool = True) -> ProveItResult:
    return ProveItResult(
        test_path="tests/test_x.py::test_y",
        fix_commit="abc1234",
        failed_before=failed_before,
        passes_after=passes_after,
    )


class TestLessonVerifier:
    def test_internal_pass_requires_red_before_green_after(self) -> None:
        ev = LessonVerifier().verify_internal(_prove_it(True, True))
        assert ev.verdict is Verdict.PASS

    def test_internal_fail_if_not_red_before(self) -> None:
        ev = LessonVerifier().verify_internal(_prove_it(failed_before=False))
        assert ev.verdict is Verdict.FAIL
        assert "NO falla" in ev.reason

    def test_internal_fail_if_not_green_after(self) -> None:
        ev = LessonVerifier().verify_internal(_prove_it(passes_after=False))
        assert ev.verdict is Verdict.FAIL
        assert "NO pasa" in ev.reason

    def test_external_pass_requires_corroboration(self) -> None:
        assert LessonVerifier().verify_external(corroborated=True).verdict is Verdict.PASS

    def test_external_fail_without_corroboration(self) -> None:
        ev = LessonVerifier().verify_external(corroborated=False, reason="solo foros")
        assert ev.verdict is Verdict.FAIL
        assert "solo foros" in ev.reason


class TestLessonStoreEntryLaw:
    def _lesson(self, verdict: str) -> Lesson:
        return Lesson(
            id="lesson-test",
            title="x",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h",
            avoid_pattern="p",
            evidence={"verdict": verdict},
        )

    def test_add_rejects_non_pass_evidence(self, store: LessonStore) -> None:
        with pytest.raises(LessonRejected, match="sin Evidence PASS"):
            store.add(self._lesson("fail"))
        with pytest.raises(LessonRejected):
            store.add(self._lesson("unknown"))

    def test_add_accepts_pass(self, store: LessonStore) -> None:
        lesson = store.add(self._lesson("pass"))
        assert store.get(lesson.id) is not None

    def test_round_trip_serialization(self, store: LessonStore) -> None:
        ev = LessonVerifier().verify_internal(_prove_it())
        lesson = Lesson(
            id="lesson-rt",
            title="matcher",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="tokens genéricos corroboran",
            avoid_pattern="igualdad literal de nombres reverse-DNS",
            evidence=ev.to_dict(),
            regression_test_path="tests/test_maintenance_analyst.py::test_generic",
            source_refs=("fix:7de8251",),
            tags=("matcher", "corroboration"),
        )
        store.add(lesson)
        got = store.get("lesson-rt")
        assert got is not None
        assert got.provenance is LessonProvenance.INTERNAL_FAILURE
        assert got.source_refs == ("fix:7de8251",)
        assert got.tags == ("matcher", "corroboration")
        # JSON-serializable para Merkle/inspección
        json.dumps(got.to_dict())


class TestLessonStoreQueries:
    def _seed(self, store: LessonStore) -> None:
        ev = LessonVerifier().verify_internal(_prove_it()).to_dict()
        ev_ext = LessonVerifier().verify_external(corroborated=True).to_dict()
        store.add(Lesson(id="a", title="A", provenance=LessonProvenance.INTERNAL_FAILURE,
                         detection_heuristic="h", avoid_pattern="p", evidence=ev, tags=("merkle",)))
        store.add(Lesson(id="b", title="B", provenance=LessonProvenance.EXTERNAL_SOURCE,
                         detection_heuristic="h", avoid_pattern="p", evidence=ev_ext, tags=("perf",)))

    def test_by_provenance(self, store: LessonStore) -> None:
        self._seed(store)
        assert [lesson.id for lesson in store.by_provenance(LessonProvenance.INTERNAL_FAILURE)] == ["a"]
        assert [lesson.id for lesson in store.by_provenance(LessonProvenance.EXTERNAL_SOURCE)] == ["b"]

    def test_search_by_tag(self, store: LessonStore) -> None:
        self._seed(store)
        assert [lesson.id for lesson in store.search_by_tag("merkle")] == ["a"]

    def test_corrupt_file_ignored(self, store: LessonStore, tmp_path: Path) -> None:
        self._seed(store)
        (tmp_path / "lessons" / "garbage.json").write_text("{not json", encoding="utf-8")
        assert len(store.all()) == 2


class TestLessonPromoter:
    def test_promote_failure_requires_prove_it(self, store: LessonStore) -> None:
        promoter = LessonPromoter(store)
        lesson = promoter.promote_failure(
            failure_id="fail-1",
            title="doble escritor Merkle",
            detection_heuristic="dos procesos escriben la misma cadena",
            avoid_pattern="CLI escribiendo Merkle con el servicio vivo",
            regression_test_path="tests/test_writer_lock.py::test_single_writer",
            prove_it=_prove_it(),
            tags=("merkle", "single-writer"),
        )
        assert lesson is not None
        assert lesson.provenance is LessonProvenance.INTERNAL_FAILURE
        assert "failure:fail-1" in lesson.source_refs
        assert store.get(lesson.id) is not None

    def test_promote_failure_returns_none_without_red_before(self, store: LessonStore) -> None:
        promoter = LessonPromoter(store)
        lesson = promoter.promote_failure(
            failure_id="fail-2",
            title="x",
            detection_heuristic="h",
            avoid_pattern="p",
            regression_test_path="tests/test_x.py::test_y",
            prove_it=_prove_it(failed_before=False),
            tags=(),
        )
        assert lesson is None
        assert store.all() == []  # no se persistió nada

    def test_ingest_external_requires_corroboration(self, store: LessonStore) -> None:
        promoter = LessonPromoter(store)
        ok = promoter.ingest_external(
            title="nuevo CVE en lib X",
            detection_heuristic="versión < 2.1 vulnerable",
            avoid_pattern="fijar lib X < 2.1",
            source_refs=("https://nvd.nist.gov/...", "https://github.com/x/advisory"),
            corroborated=True,
            tags=("cve", "deps"),
        )
        assert ok is not None
        assert ok.provenance is LessonProvenance.EXTERNAL_SOURCE

        rejected = promoter.ingest_external(
            title="rumor de foro",
            detection_heuristic="h",
            avoid_pattern="p",
            source_refs=("https://forum/...",),
            corroborated=False,
            reason="solo señal de foro, sin fuente autoritativa",
        )
        assert rejected is None
        assert len(store.all()) == 1  # solo la corroborada


class TestMerkleLogging:
    def test_add_logs_to_merkle(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(tmp_path / "merkle")
        store = LessonStore(tmp_path / "lessons", merkle=merkle)
        ev = LessonVerifier().verify_external(corroborated=True).to_dict()
        store.add(Lesson(id="m", title="t", provenance=LessonProvenance.EXTERNAL_SOURCE,
                         detection_heuristic="h", avoid_pattern="p", evidence=ev))
        actions = [r.to_dict()["action"] for r in merkle.tail(5)]
        assert "lesson.recorded" in actions


class TestFailureBackLink:
    def test_failure_entry_carries_lesson_back_link(self) -> None:
        from atlas.memory.memory_system import FailureEntry

        fe = FailureEntry(
            id="f1", error_type="E", description="d", context={}, solution="s",
            promoted_to_lesson_id="lesson-xyz",
        )
        assert fe.to_dict()["promoted_to_lesson_id"] == "lesson-xyz"
        # Compat: ficheros viejos sin el campo se reconstruyen con None
        old = {"id": "f0", "error_type": "E", "description": "d",
               "context": {}, "solution": "s", "tags": [], "occurred_at": "t"}
        assert FailureEntry(**old).promoted_to_lesson_id is None
