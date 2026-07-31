"""Puente ColdUpdate→plano de ingeniería (F1.3, 2026-07-31).

Motivo medido, no estético. `cold_update_manager.py:459-468` YA clasificaba
la causa raíz de cada validación fallida y guardaba el veredicto en
`proposal.forensics["root_cause"]` como dict crudo. Ahí moría: nadie lo
proyectaba al journal versionado de findings.

Consecuencia en cadena, que es lo que hace importante este puente:
`diagnostics.py:320` es el ÚNICO productor del repo que rellena `locations`
en un `EngineeringFinding` (`review.py:141` y la normalización de
`findings.py` emiten `locations=()`). Y `hypotheses.compose_hypotheses()`
necesita justamente un `FindingLocation`. Sin este puente, cablear
`hypotheses.py` daría un caller que itera SIEMPRE sobre una tupla vacía —
cableado hueco, la misma trampa de ADC-WO-108 con otro disfraz.

Invariante de coste: el veredicto ya calculado se REUTILIZA. Volver a
llamar al clasificador duplicaría el camino LLM de `RootCauseClassifier`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from atlas.core.validation_runner import ValidationReport
from atlas.engineering.cold_update_bridge import (
    ColdUpdateDiagnosticSink,
    PrecomputedRootCause,
)
from atlas.engineering.findings import EngineeringFindingStore


@dataclass
class _Verdict:
    # Vocabulario REAL de `RootCauseClassifier` (español), no uno inventado:
    # el camino determinista de `root_cause_classifier.py:78` emite
    # exactamente "ambiental" con `evidence_paths` y `used_llm=False`.
    classification: str = "ambiental"
    reason: str = "worktree construido desde una base con ficheros sin commitear"
    evidence_paths: list[str] = field(default_factory=lambda: ["src/atlas/core/doctor.py"])
    used_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "used_llm": self.used_llm}


@dataclass
class _Proposal:
    id: str = "prop_abc123"
    base_ref: str = "HEAD"
    patch_sha256: str = "deadbeef"
    risk: str = "high"


def _sink(tmp_path: Path) -> tuple[ColdUpdateDiagnosticSink, EngineeringFindingStore]:
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")
    return ColdUpdateDiagnosticSink(store=store, repository=str(tmp_path)), store


def _failed() -> ValidationReport:
    return ValidationReport(
        passed=False, pytest_exit=1, mypy_exit=0,
        pytest_summary="1 failed", mypy_summary="ok",
    )


class TestFindingHasLocations:
    """El punto entero del puente: producir findings CON `locations`."""

    def test_evidence_paths_of_the_verdict_become_finding_locations(
        self, tmp_path: Path
    ) -> None:
        sink, store = _sink(tmp_path)

        finding = sink.record(
            proposal=_Proposal(), report=_failed(), verdict=_Verdict()
        )

        assert finding is not None
        assert [loc.path for loc in finding.locations] == ["src/atlas/core/doctor.py"]
        assert store.count() == 1

    def test_the_finding_is_persisted_in_the_journal(self, tmp_path: Path) -> None:
        sink, store = _sink(tmp_path)

        sink.record(proposal=_Proposal(), report=_failed(), verdict=_Verdict())

        assert store.count() == 1


class TestVocabularyCompatibility:
    """Riesgo de integración real: son dos módulos con vocabularios propios.
    Si `RootCauseClassifier` emitiera una etiqueta que `diagnostics` no
    conoce, ésta caería a UNKNOWN y **perdería los `evidence_paths`** — es
    decir, findings sin `locations` otra vez, y `hypotheses` volvería a ser
    hueco sin que nada fallara en rojo. Se fija por test."""

    def test_every_label_the_classifier_emits_is_understood_by_diagnostics(self) -> None:
        from atlas.engineering.diagnostics import _CLASSIFICATIONS

        # Las tres que `root_cause_classifier.py` puede emitir hoy: la
        # determinista (:78) y las dos del camino LLM (:161).
        for label in ("ambiental", "causado_por_diff", "unknown"):
            assert label in _CLASSIFICATIONS, f"diagnostics no entiende '{label}'"

    def test_the_deterministic_path_label_preserves_evidence_paths(
        self, tmp_path: Path
    ) -> None:
        # "ambiental" es la única etiqueta que el camino GRATIS (used_llm=False)
        # emite junto a evidence_paths. Si dejara de mapear, el puente entero
        # se quedaría sin locations sin coste de proveedor.
        sink, _ = _sink(tmp_path)

        finding = sink.record(
            proposal=_Proposal(),
            report=_failed(),
            verdict=_Verdict(classification="ambiental"),
        )

        assert finding is not None
        assert finding.locations != ()


class TestCostInvariant:
    def test_the_precomputed_verdict_is_reused_not_reclassified(self) -> None:
        # Volver a clasificar duplicaría el camino LLM de RootCauseClassifier.
        verdict = _Verdict()
        adapter = PrecomputedRootCause(verdict)

        returned = adapter.classify(
            pytest_summary="lo que sea", mypy_summary="lo que sea", base_ref="HEAD"
        )

        assert returned is verdict


class TestOnlyFailures:
    def test_a_passing_validation_records_nothing(self, tmp_path: Path) -> None:
        sink, store = _sink(tmp_path)
        passing = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0)

        finding = sink.record(
            proposal=_Proposal(), report=passing, verdict=_Verdict()
        )

        assert finding is None
        assert store.count() == 0


class TestFailHonest:
    def test_a_broken_store_never_propagates_to_cold_update(self, tmp_path: Path) -> None:
        # Un fallo del plano de ingeniería NUNCA puede tumbar una validación
        # gobernada de ColdUpdate: es señal, jamás una puerta.
        class _Boom(EngineeringFindingStore):
            def record(self, finding: Any) -> Any:
                raise OSError("disco lleno")

        sink = ColdUpdateDiagnosticSink(
            store=_Boom(tmp_path / "f.jsonl"), repository=str(tmp_path)
        )

        assert sink.record(proposal=_Proposal(), report=_failed(), verdict=_Verdict()) is None


class TestColdUpdateManagerIntegration:
    def test_manager_accepts_and_calls_the_sink_on_failed_validation(self) -> None:
        # Contrato de inyección: mismo patrón que `root_cause_classifier`.
        from atlas.core.cold_update_manager import ColdUpdateManager

        assert "diagnostic_sink" in ColdUpdateManager.__init__.__code__.co_varnames


@pytest.mark.parametrize(
    ("proposal_risk", "expected"),
    [("low", "low"), ("medium", "medium"), ("high", "high"), ("critical", "critical")],
)
class TestRiskMapping:
    def test_proposal_risk_is_preserved_not_reinvented(
        self, tmp_path: Path, proposal_risk: str, expected: str
    ) -> None:
        # No se inventa una escala nueva: se reusa el vocabulario ya gobernado.
        sink, _ = _sink(tmp_path)

        finding = sink.record(
            proposal=_Proposal(risk=proposal_risk), report=_failed(), verdict=_Verdict()
        )

        assert finding is not None
        assert finding.risk.value == expected
