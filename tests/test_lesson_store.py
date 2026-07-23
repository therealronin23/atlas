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
from atlas.memory.memory_system import ErrorRegistry, FailureEntry


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


class TestPromoteFailureClosesErrorRegistryLoop:
    """Capa 4 backlog t1-error-registry-lesson-promotion: `promoted_to_lesson_id`
    existía en FailureEntry pero nada lo asignaba. Round-trip completo: fallo
    registrado -> promovido -> la entrada de ErrorRegistry referencia la lección."""

    def _record_failure(self, registry: ErrorRegistry, *, failure_id: str) -> FailureEntry:
        entry = FailureEntry(
            id=failure_id,
            error_type="writer_lock",
            description="dos procesos escriben la misma cadena Merkle",
            context={"pid_a": 1, "pid_b": 2},
            solution="single-writer con lock de fichero",
        )
        registry.record(entry)
        return entry

    def _get(self, registry: ErrorRegistry, failure_id: str) -> FailureEntry:
        matches = [e for e in registry.all() if e.id == failure_id]
        assert len(matches) == 1
        return matches[0]

    def test_successful_promotion_marks_error_registry_entry(
        self, store: LessonStore, tmp_path: Path
    ) -> None:
        registry = ErrorRegistry(tmp_path / "error_registry")
        self._record_failure(registry, failure_id="fail-round-trip")
        promoter = LessonPromoter(store, error_registry=registry)

        lesson = promoter.promote_failure(
            failure_id="fail-round-trip",
            title="doble escritor Merkle",
            detection_heuristic="dos procesos escriben la misma cadena",
            avoid_pattern="CLI escribiendo Merkle con el servicio vivo",
            regression_test_path="tests/test_writer_lock.py::test_single_writer",
            prove_it=_prove_it(),
        )

        assert lesson is not None
        updated = self._get(registry, "fail-round-trip")
        assert updated.promoted_to_lesson_id == lesson.id

    def test_failed_promotion_does_not_touch_error_registry(
        self, store: LessonStore, tmp_path: Path
    ) -> None:
        registry = ErrorRegistry(tmp_path / "error_registry")
        self._record_failure(registry, failure_id="fail-no-prove-it")
        promoter = LessonPromoter(store, error_registry=registry)

        lesson = promoter.promote_failure(
            failure_id="fail-no-prove-it",
            title="x",
            detection_heuristic="h",
            avoid_pattern="p",
            regression_test_path="tests/test_x.py::test_y",
            prove_it=_prove_it(failed_before=False),
        )

        assert lesson is None
        untouched = self._get(registry, "fail-no-prove-it")
        assert untouched.promoted_to_lesson_id is None

    def test_promotion_without_error_registry_still_works(self, store: LessonStore) -> None:
        """error_registry sigue siendo opcional: no romper a los llamadores
        existentes que construyen LessonPromoter(store) sin él."""
        promoter = LessonPromoter(store)
        lesson = promoter.promote_failure(
            failure_id="fail-no-registry",
            title="x",
            detection_heuristic="h",
            avoid_pattern="p",
            regression_test_path="tests/test_x.py::test_y",
            prove_it=_prove_it(),
        )
        assert lesson is not None


class TestRecordRecurring:
    """record_recurring: fallos que se repiten suben occurrence_count en la
    MISMA lección (buscada por tag dedup:<key>) en vez de crear un archivo
    nuevo por cada repetición — el gap que señaló el Cónclave (38 archivos
    casi idénticos para el mismo bug de YAML)."""

    def _record_via_store(self, store: LessonStore, *, dedup_key: str) -> Lesson:
        return store.record_recurring(
            dedup_key=dedup_key,
            title="Fallo recurrente: rompe suite combinada",
            detection_heuristic="mismo intent+motivo ya visto",
            avoid_pattern="proposal X — motivo: rompe la suite combinada",
            evidence={},
            tags=(),
        )

    def test_first_occurrence_creates_lesson_with_count_1(self, store: LessonStore) -> None:
        lesson = self._record_via_store(store, dedup_key="k1")
        assert lesson.occurrence_count == 1
        assert f"dedup:k1" in lesson.tags
        assert len(store.all()) == 1

    def test_second_occurrence_reuses_same_file_and_bumps_count(self, store: LessonStore) -> None:
        first = self._record_via_store(store, dedup_key="k1")
        second = self._record_via_store(store, dedup_key="k1")
        assert second.id == first.id
        assert second.occurrence_count == 2
        assert second.last_seen_at != ""
        # Sigue habiendo solo UNA lección con este dedup tag, no un archivo nuevo
        matches = store.search_by_tag("dedup:k1")
        assert len(matches) == 1
        assert matches[0].occurrence_count == 2

    def test_third_occurrence_bumps_count_to_3(self, store: LessonStore) -> None:
        self._record_via_store(store, dedup_key="k1")
        self._record_via_store(store, dedup_key="k1")
        third = self._record_via_store(store, dedup_key="k1")
        assert third.occurrence_count == 3
        assert len(store.search_by_tag("dedup:k1")) == 1

    def test_distinct_dedup_key_creates_separate_lesson(self, store: LessonStore) -> None:
        self._record_via_store(store, dedup_key="k1")
        other = self._record_via_store(store, dedup_key="k2")
        assert other.occurrence_count == 1
        assert len(store.all()) == 2

    def test_from_dict_defaults_for_lessons_saved_before_this_change(self) -> None:
        old_json = {
            "id": "lesson-old",
            "title": "t",
            "provenance": "internal_failure",
            "detection_heuristic": "h",
            "avoid_pattern": "p",
            "evidence": {"verdict": "pass"},
            # sin occurrence_count ni last_seen_at — lección pre-existente
        }
        lesson = Lesson.from_dict(old_json)
        assert lesson.occurrence_count == 1
        assert lesson.last_seen_at == ""


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
