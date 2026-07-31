"""Correction production for an engineering finding (ADC-WO-108, piece 5/5).

Non-negotiable invariant from the work order itself: **"no patch application
from a finding."** This module never writes, applies, or synthesizes a
patch. It composes a finding's own already-carried evidence (its
``patch_ref``) with the governed proposal path that already exists --
``ColdUpdateManager.propose()`` -- which stages the patch into an ISOLATED
worktree in ``proposed`` status and requires human approval before anything
touches the real repository (``ColdUpdateManager.approve``/``apply``, never
called from here).

A finding without a ``patch_ref`` has nothing to propose: that is a correct,
fail-honest outcome, not an error to work around by generating one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from atlas.engineering.findings import EngineeringFinding, FindingSeverity

# Mapeo a la severidad -> el vocabulario de riesgo YA gobernado por
# ColdUpdateManager._validate_risk ("low", "medium", "high", "critical") --
# no se inventa una escala nueva.
_RISK_BY_SEVERITY: dict[FindingSeverity, str] = {
    FindingSeverity.INFO: "low",
    FindingSeverity.MINOR: "medium",
    FindingSeverity.MAJOR: "high",
    FindingSeverity.BLOCKING: "critical",
}


class _ColdUpdateProposalLike(Protocol):
    id: str
    status: str


class ColdUpdateManagerLike(Protocol):
    """The stable seam implemented by ``ColdUpdateManager.propose`` today."""

    def propose(
        self,
        intent: str,
        patch_path: Path,
        *,
        base_ref: str = "HEAD",
        origin: str = "manual",
        risk: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> _ColdUpdateProposalLike: ...


@dataclass(frozen=True)
class CorrectionOutcome:
    proposed: bool
    finding_id: str = ""
    proposal_id: str = ""
    status: str = ""
    reason: str = ""


def propose_correction(
    finding: EngineeringFinding,
    *,
    manager: ColdUpdateManagerLike,
    base_ref: str = "HEAD",
) -> CorrectionOutcome:
    """Route a finding's own patch reference through the governed ColdUpdate
    proposal path. Never applies, never approves -- only ``propose()``."""
    if finding.patch_ref is None:
        return CorrectionOutcome(
            proposed=False, finding_id=finding.id,
            reason="finding sin patch_ref: nada que proponer (no se sintetiza uno)",
        )
    patch_path = Path(finding.patch_ref)
    if not patch_path.is_file():
        return CorrectionOutcome(
            proposed=False, finding_id=finding.id,
            reason=f"patch_ref no es un fichero legible: {patch_path}",
        )

    proposal = manager.propose(
        intent=finding.summary,
        patch_path=patch_path,
        base_ref=base_ref,
        # "self_audit" es el origin ya gobernado más cercano a "una tubería
        # automatizada de revisión produjo esto" -- no se amplía el
        # vocabulario de ColdUpdateManager sin necesidad real.
        origin="self_audit",
        risk=_RISK_BY_SEVERITY[finding.severity],
        evidence={
            "finding_id": finding.id,
            "dedupe_key": finding.dedupe_key,
            "source": finding.source,
            "category": finding.category,
            "candidate_revision": finding.candidate_revision,
        },
    )
    return CorrectionOutcome(
        proposed=True, finding_id=finding.id,
        proposal_id=proposal.id, status=proposal.status,
    )
