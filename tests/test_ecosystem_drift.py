"""Detector de deriva mapa-del-ecosistema↔disco (spec B+C §5, MAXIMUS
Cycle 13). "Pieza en disco sin fila en el mapa" se traduce, determinista, a:
¿todo ADR real tiene su número citado en algún sitio de
`docs/design/atlas_ecosystem_map.md`? Los ADR ya son el mecanismo
establecido de este repo para "decisión de arquitectura/capacidad", y el
propio mapa ya los cita como Evidence/Authority en casi todas sus filas —
reusar esa convención evita inventar un vocabulario nuevo.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.self_maintenance.ecosystem_drift import ecosystem_map_drift


def _write_adr(repo: Path, name: str) -> None:
    path = repo / "docs" / "decisions" / "adr" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n", encoding="utf-8")


def _write_map(repo: Path, text: str) -> None:
    path = repo / "docs" / "design" / "atlas_ecosystem_map.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestReferencedAdrsAreNotFlagged:
    def test_individually_cited_adr_has_no_finding(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_072_supply_chain_admission_scan.md")
        _write_map(tmp_path, "| Item | ... | ADR-072 |\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_citation_with_underscore_style_also_counts(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_072_supply_chain_admission_scan.md")
        _write_map(tmp_path, "see docs/decisions/adr/adr_072_supply_chain_admission_scan.md\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_case_insensitive_citation_counts(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_072_supply_chain_admission_scan.md")
        _write_map(tmp_path, "closed under adr-072\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_letter_suffixed_adr_matches_exactly(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_013b_computer_use.md")
        _write_map(tmp_path, "gated by ADR-013b\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_letter_suffixed_adr_not_satisfied_by_base_number_citation(
        self, tmp_path: Path
    ) -> None:
        # ADR-013 (sin b) citado no debe dar por bueno a ADR-013b — son
        # documentos distintos.
        _write_adr(tmp_path, "adr_013b_computer_use.md")
        _write_map(tmp_path, "see ADR-013\n")

        findings = ecosystem_map_drift(tmp_path)
        assert len(findings) == 1
        assert "ADR-013b" in findings[0]


class TestRangeCitations:
    def test_adr_within_inclusive_range_is_not_flagged(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_031_agentic_tool_loop.md")
        _write_map(tmp_path, "governance base | ADR-024..040 | sealed\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_range_endpoints_are_inclusive(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_024_a.md")
        _write_adr(tmp_path, "adr_040_b.md")
        _write_map(tmp_path, "ADR-024..040\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_adr_outside_range_is_still_flagged(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_041_universal_verifier.md")
        _write_map(tmp_path, "ADR-024..040\n")

        findings = ecosystem_map_drift(tmp_path)
        assert len(findings) == 1
        assert "ADR-041" in findings[0]


class TestUnreferencedAdrsAreFlagged:
    def test_uncited_adr_produces_a_finding(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_099_something.md")
        _write_map(tmp_path, "no menciona nada relevante aquí\n")

        findings = ecosystem_map_drift(tmp_path)

        assert len(findings) == 1
        assert "ADR-099" in findings[0]
        assert "adr_099_something.md" in findings[0]

    def test_multiple_adrs_only_uncited_ones_flagged(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_001_cited.md")
        _write_adr(tmp_path, "adr_002_uncited.md")
        _write_map(tmp_path, "referencia a ADR-001 y nada más\n")

        findings = ecosystem_map_drift(tmp_path)

        assert len(findings) == 1
        assert "ADR-002" in findings[0]


class TestFailHonest:
    def test_missing_map_file_flags_every_adr(self, tmp_path: Path) -> None:
        _write_adr(tmp_path, "adr_001_a.md")
        _write_adr(tmp_path, "adr_002_b.md")
        # sin escribir el mapa

        findings = ecosystem_map_drift(tmp_path)

        assert len(findings) == 2

    def test_no_adrs_at_all_is_empty_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "docs" / "design").mkdir(parents=True)
        _write_map(tmp_path, "mapa vacío de ADRs\n")

        assert ecosystem_map_drift(tmp_path) == []

    def test_non_adr_markdown_files_in_adr_dir_are_ignored(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "decisions" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "README.md").write_text("# convención de nombres\n", encoding="utf-8")
        _write_map(tmp_path, "sin nada\n")

        assert ecosystem_map_drift(tmp_path) == []


class TestRealRepoIntegration:
    def test_real_repo_map_has_no_completely_unreferenced_range_math_error(self) -> None:
        # No afirma "cero drift" (sería un falso claim de limpieza) — solo
        # que el detector corre limpio sobre el repo real sin reventar y
        # que los ADRs recién corregidos hoy (072/073) SÍ cuentan como
        # citados, confirmando que la lógica de citación individual funciona
        # contra el fichero real, no solo fixtures sintéticas.
        real_root = Path(__file__).resolve().parent.parent
        findings = ecosystem_map_drift(real_root)

        assert isinstance(findings, list)
        joined = "\n".join(findings)
        assert "ADR-072" not in joined
        assert "ADR-073" not in joined
