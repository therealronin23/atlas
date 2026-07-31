"""Contract tests para la producción de correcciones (ADC-WO-108, pieza 5/5).

Invariante NO NEGOCIABLE del propio work order: "no patch application from
a finding". Este módulo nunca aplica nada -- compone un finding con su
propio `patch_ref` (evidencia que el finding YA carga, nunca sintetizada
aquí) y lo somete a `ColdUpdateManager.propose()`, la ruta gobernada
existente. `propose()` deja el patch en un worktree AISLADO en estado
`proposed`, esperando aprobación humana -- nunca toca el árbol real. Si el
finding no trae `patch_ref`, no hay nada que proponer: fail-honesto, no se
inventa un patch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.engineering.correction import (
    CorrectionOutcome,
    propose_correction,
)
from atlas.engineering.findings import (
    EngineeringFinding,
    FindingEvidence,
    FindingLocation,
    FindingSeverity,
    FindingStatus,
)


def _finding(*, patch_ref: str | None, severity: FindingSeverity = FindingSeverity.MAJOR) -> EngineeringFinding:
    return EngineeringFinding(
        id="finding_correction_001",
        run_id="run_001",
        task_id=None,
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        source="ast_guard",
        category="security",
        severity=severity,
        status=FindingStatus.OPEN,
        summary="Import no permitido en el parche generado",
        detail="detalle",
        locations=(FindingLocation(path="src/atlas/core/example.py", start_line=7),),
        evidence=(FindingEvidence(kind="test", reference="tests/test_x.py", detail="d"),),
        reproduction=None,
        suggested_action="Quitar el import",
        patch_ref=patch_ref,
        dedupe_key="atlas-core:abc:ast_guard:src/atlas/core/example.py:7",
        created_at="2026-07-31T00:00:00+00:00",
        updated_at="2026-07-31T00:00:00+00:00",
    )


class _FakeProposal:
    def __init__(self, proposal_id: str) -> None:
        self.id = proposal_id
        self.status = "proposed"


class _FakeColdUpdateManager:
    """Doble de ColdUpdateManager.propose() -- nunca toca disco de verdad."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def propose(self, intent, patch_path, *, base_ref="HEAD", origin="manual", risk="medium", evidence=None):
        self.calls.append({
            "intent": intent, "patch_path": patch_path, "base_ref": base_ref,
            "origin": origin, "risk": risk, "evidence": evidence,
        })
        return _FakeProposal("cu_" + str(len(self.calls)))


def test_finding_without_patch_ref_proposes_nothing(tmp_path: Path) -> None:
    finding = _finding(patch_ref=None)
    manager = _FakeColdUpdateManager()

    outcome = propose_correction(finding, manager=manager)

    assert isinstance(outcome, CorrectionOutcome)
    assert outcome.proposed is False
    assert "patch_ref" in outcome.reason
    assert manager.calls == []


def test_finding_with_unreadable_patch_ref_proposes_nothing(tmp_path: Path) -> None:
    finding = _finding(patch_ref=str(tmp_path / "no-existe.patch"))
    manager = _FakeColdUpdateManager()

    outcome = propose_correction(finding, manager=manager)

    assert outcome.proposed is False
    assert manager.calls == []


def test_finding_with_real_patch_ref_routes_through_governed_propose(tmp_path: Path) -> None:
    patch = tmp_path / "candidate.patch"
    patch.write_text("--- a/x\n+++ b/x\n@@\n-old\n+new\n", encoding="utf-8")
    finding = _finding(patch_ref=str(patch), severity=FindingSeverity.MAJOR)
    manager = _FakeColdUpdateManager()

    outcome = propose_correction(finding, manager=manager)

    assert outcome.proposed is True
    assert outcome.proposal_id == "cu_1"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["patch_path"] == patch
    # Vocabulario gobernado ya existente -- nunca se inventa un origin nuevo.
    assert call["origin"] == "self_audit"
    assert call["evidence"]["finding_id"] == finding.id


@pytest.mark.parametrize(
    "severity,expected_risk",
    [
        (FindingSeverity.INFO, "low"),
        (FindingSeverity.MINOR, "medium"),
        (FindingSeverity.MAJOR, "high"),
        (FindingSeverity.BLOCKING, "critical"),
    ],
)
def test_severity_maps_to_governed_risk_vocabulary(
    tmp_path: Path, severity: FindingSeverity, expected_risk: str,
) -> None:
    patch = tmp_path / "candidate.patch"
    patch.write_text("--- a/x\n+++ b/x\n@@\n-old\n+new\n", encoding="utf-8")
    finding = _finding(patch_ref=str(patch), severity=severity)
    manager = _FakeColdUpdateManager()

    propose_correction(finding, manager=manager)

    assert manager.calls[0]["risk"] == expected_risk


def test_propose_correction_never_calls_apply_or_approve(tmp_path: Path) -> None:
    """El invariante no negociable del WO, verificado por ausencia: el doble
    de ColdUpdateManager NO TIENE métodos apply/approve -- si
    propose_correction intentara llamarlos, este test fallaría con
    AttributeError, no con una aserción explícita que se pueda desactivar
    sin querer."""
    patch = tmp_path / "candidate.patch"
    patch.write_text("--- a/x\n+++ b/x\n@@\n-old\n+new\n", encoding="utf-8")
    finding = _finding(patch_ref=str(patch))
    manager = _FakeColdUpdateManager()

    outcome = propose_correction(finding, manager=manager)

    assert outcome.proposed is True
    assert outcome.status == "proposed"
