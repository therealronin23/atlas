"""Pase de hipótesis sobre el journal de findings (F1.1, 2026-07-31).

`hypotheses.py` (211 loc) llevaba dormido desde que se escribió, y NO por
descuido: `compose_hypotheses()` exige un `FindingLocation`, y hasta F1.3
ningún productor de producción rellenaba `locations` (`review.py:141` y la
normalización de `findings.py` emiten `locations=()`). Cablearlo antes de
F1.3 habría dado un caller que itera siempre sobre una tupla vacía.

Con el puente ColdUpdate ya vivo, el journal contiene findings CON
localizaciones reales, y este pase tiene sobre qué trabajar de verdad.
"""

from __future__ import annotations

from pathlib import Path

from atlas.engineering.findings import (
    EngineeringFinding,
    EngineeringFindingStore,
    FindingEvidence,
    FindingLocation,
    FindingSeverity,
    FindingStatus,
)
from atlas.engineering.hypotheses import compose_for_findings


def _finding(
    finding_id: str,
    *,
    paths: tuple[str, ...],
    status: FindingStatus = FindingStatus.OPEN,
) -> EngineeringFinding:
    return EngineeringFinding(
        # El modelo exige `^finding_[A-Za-z0-9_-]+$`.
        id=f"finding_{finding_id}",
        run_id="run-1",
        task_id=None,
        repository="/repo",
        base_revision="HEAD",
        candidate_revision="cand",
        source="diagnostic_coordinator",
        category="validation_diagnostic",
        severity=FindingSeverity.MAJOR,
        status=status,
        summary="fallo de validación",
        detail="detalle",
        locations=tuple(FindingLocation(path=p) for p in paths),
        evidence=(FindingEvidence(kind="k", reference="r", detail="d"),),
        reproduction=None,
        suggested_action=None,
        patch_ref=None,
        dedupe_key=f"dk-{finding_id}",
        created_at="2026-07-31T00:00:00+00:00",
        updated_at="2026-07-31T00:00:00+00:00",
    )


class _Store:
    """LessonStore mínimo: el pase no debe exigir un índice real."""

    def search_by_tag(self, tag: str, limit: int = 5) -> list[object]:
        return []


class TestComposesOnlyWhereThereIsSomethingToCompose:
    def test_a_finding_with_locations_produces_one_set_per_location(
        self, tmp_path: Path
    ) -> None:
        findings = [_finding("f1", paths=("src/atlas/core/doctor.py",))]

        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "graph.kuzu",
            lesson_store=_Store(),
        )

        assert len(sets) == 1
        assert sets[0].location.path == "src/atlas/core/doctor.py"

    def test_a_finding_without_locations_is_skipped(self, tmp_path: Path) -> None:
        # Es el caso de TODO finding de `review.py` -- no es un error, no hay
        # nada que hipotetizar sin una localización.
        findings = [_finding("f1", paths=())]

        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "graph.kuzu",
            lesson_store=_Store(),
        )

        assert sets == []

    def test_resolved_findings_are_skipped(self, tmp_path: Path) -> None:
        findings = [
            _finding("f1", paths=("src/atlas/a.py",), status=FindingStatus.RESOLVED)
        ]

        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "graph.kuzu",
            lesson_store=_Store(),
        )

        assert sets == []


class TestFailHonest:
    def test_a_missing_graph_never_hides_the_other_sources(self, tmp_path: Path) -> None:
        # `graph.kuzu` no existe: el grafo debe reportarse no disponible CON
        # motivo, y history/memory deben seguir respondiendo.
        findings = [_finding("f1", paths=("src/atlas/core/doctor.py",))]

        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "no-existe.kuzu",
            lesson_store=_Store(),
        )

        assert len(sets) == 1
        assert sets[0].graph.available is False
        assert sets[0].graph.reason

    def test_one_broken_finding_does_not_abort_the_pass(self, tmp_path: Path) -> None:
        findings = [
            _finding("f1", paths=("src/atlas/core/doctor.py",)),
            _finding("f2", paths=("src/atlas/core/other.py",)),
        ]

        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "no-existe.kuzu",
            lesson_store=_Store(),
        )

        assert len(sets) == 2


class TestPersistence:
    def test_sets_are_written_as_jsonl(self, tmp_path: Path) -> None:
        from atlas.engineering.hypotheses import write_hypotheses

        findings = [_finding("f1", paths=("src/atlas/core/doctor.py",))]
        sets = compose_for_findings(
            findings,
            repo_root=tmp_path,
            graph_db_path=tmp_path / "no-existe.kuzu",
            lesson_store=_Store(),
        )
        out = tmp_path / "hypotheses.jsonl"

        written = write_hypotheses(sets, out)

        assert written == 1
        assert out.is_file()
        assert "src/atlas/core/doctor.py" in out.read_text(encoding="utf-8")


class TestStoreIntegration:
    def test_the_pass_reads_the_same_journal_the_bridge_writes(
        self, tmp_path: Path
    ) -> None:
        # Un solo journal: si el puente y el pase miraran ficheros distintos,
        # el pase no vería nunca los findings con locations.
        store = EngineeringFindingStore(tmp_path / "findings.jsonl")
        store.record(_finding("f1", paths=("src/atlas/core/doctor.py",)))

        sets = compose_for_findings(
            store.list(),
            repo_root=tmp_path,
            graph_db_path=tmp_path / "no-existe.kuzu",
            lesson_store=_Store(),
        )

        assert len(sets) == 1
