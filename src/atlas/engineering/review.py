"""Deterministic composition of existing verification seams into findings.

The coordinator owns neither verification policy nor effects.  It receives
adapter outcomes, verifies that they belong to the requested review context,
and persists only the resulting EngineeringFinding projection.  A reviewer
exception remains UNKNOWN rather than becoming an implicit PASS.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Protocol

from atlas.core.verify import Artifact, ArtifactKind, CostTier, Evidence, UniversalVerifier, Verdict
from atlas.engineering.findings import (
    EngineeringFinding,
    EngineeringFindingStore,
    FindingEvidence,
    FindingSeverity,
    FindingStatus,
)
from atlas.events.schemas import Risk


@dataclass(frozen=True)
class EngineeringReviewRequest:
    """Inputs that identify one bounded review; no repository is opened here."""

    run_id: str
    task_id: str | None
    mission_id: str | None
    repository: str
    base_revision: str | None
    candidate_revision: str | None
    diff: str
    scope: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    at: str
    producer_cost: CostTier = CostTier.MODEL


@dataclass(frozen=True)
class ReviewOutcome:
    """One adapter result, preserving PASS/FAIL/UNKNOWN evidence semantics."""

    adapter_id: str
    verdict: Verdict
    findings: tuple[EngineeringFinding, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class EngineeringReviewReport:
    request: EngineeringReviewRequest
    verdict: Verdict
    outcomes: tuple[ReviewOutcome, ...]
    findings: tuple[EngineeringFinding, ...]


class ReviewAdapter(Protocol):
    adapter_id: str

    def review(self, request: EngineeringReviewRequest) -> ReviewOutcome: ...


class UniversalVerifierReviewAdapter:
    """Projects the existing UniversalVerifier seam; it does not replace it."""

    def __init__(
        self,
        *,
        adapter_id: str,
        verifier: UniversalVerifier,
        severity_on_fail: FindingSeverity = FindingSeverity.MAJOR,
    ) -> None:
        if not adapter_id.strip():
            raise ValueError("review adapter id cannot be empty")
        self.adapter_id = adapter_id
        self._verifier = verifier
        self._severity_on_fail = severity_on_fail

    def review(self, request: EngineeringReviewRequest) -> ReviewOutcome:
        metadata: dict[str, object] = {}
        if request.scope:
            metadata["allowed_paths"] = list(request.scope)
        artifact = Artifact(
            kind=ArtifactKind.PATCH,
            payload={"diff": request.diff},
            producer_cost=request.producer_cost,
            metadata=metadata,
        )
        evidence = self._verifier.verify(artifact)
        if evidence.verdict is not Verdict.FAIL:
            return ReviewOutcome(
                adapter_id=self.adapter_id,
                verdict=evidence.verdict,
                reason=evidence.reason,
            )
        return ReviewOutcome(
            adapter_id=self.adapter_id,
            verdict=Verdict.FAIL,
            findings=(self._finding_from_evidence(request, evidence),),
            reason=evidence.reason,
        )

    def _finding_from_evidence(
        self,
        request: EngineeringReviewRequest,
        evidence: Evidence,
    ) -> EngineeringFinding:
        reason = evidence.reason or "deterministic verification failed"
        fingerprint_source = "\x00".join(
            (
                request.repository,
                request.candidate_revision or "unknown",
                self.adapter_id,
                reason,
                ",".join(evidence.verifier_ids),
            )
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
        safe_adapter_id = "".join(
            character if character.isalnum() or character in "_-" else "_"
            for character in self.adapter_id
        )
        risk = Risk.HIGH if self._severity_on_fail is FindingSeverity.BLOCKING else Risk.MEDIUM
        evidence_reference = ",".join(evidence.verifier_ids) or self.adapter_id
        return EngineeringFinding(
            id=f"finding_{safe_adapter_id}_{fingerprint}",
            run_id=request.run_id,
            task_id=request.task_id,
            repository=request.repository,
            base_revision=request.base_revision,
            candidate_revision=request.candidate_revision,
            source=self.adapter_id,
            category="deterministic_review",
            severity=self._severity_on_fail,
            status=FindingStatus.OPEN,
            summary=f"{self.adapter_id} rejected the candidate review",
            detail=reason,
            locations=(),
            evidence=(
                FindingEvidence(
                    kind="universal_verifier",
                    reference=evidence_reference,
                    detail=reason,
                ),
            ),
            reproduction=None,
            suggested_action="Inspect deterministic verification evidence before proposing a patch.",
            patch_ref=None,
            dedupe_key=(
                f"{request.repository}:{request.candidate_revision or 'unknown'}:"
                f"{self.adapter_id}:{fingerprint}"
            ),
            created_at=request.at,
            updated_at=request.at,
            risk=risk,
        )


class EngineeringReviewCoordinator:
    """Runs adapters deterministically and stores only in-context findings."""

    def __init__(self, *, store: EngineeringFindingStore, adapters: list[ReviewAdapter]) -> None:
        adapter_ids = [adapter.adapter_id for adapter in adapters]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("engineering review adapter ids must be unique")
        self._store = store
        self._adapters = tuple(sorted(adapters, key=lambda adapter: adapter.adapter_id))

    def review(self, request: EngineeringReviewRequest) -> EngineeringReviewReport:
        outcomes: list[ReviewOutcome] = []
        recorded: list[EngineeringFinding] = []
        for adapter in self._adapters:
            try:
                outcome = adapter.review(request)
            except Exception as exc:  # noqa: BLE001 - un revisor caído debe ser visible
                outcomes.append(
                    ReviewOutcome(
                        adapter_id=adapter.adapter_id,
                        verdict=Verdict.UNKNOWN,
                        reason=(
                            f"reviewer {adapter.adapter_id} failed with {type(exc).__name__}"
                        ),
                    )
                )
                continue
            if outcome.adapter_id != adapter.adapter_id:
                outcomes.append(self._unknown(adapter.adapter_id, "returned a mismatched adapter id"))
                continue
            if outcome.verdict is not Verdict.FAIL and outcome.findings:
                outcomes.append(self._unknown(adapter.adapter_id, "returned findings without a failing verdict"))
                continue
            if not self._findings_match_request(outcome.findings, request, adapter.adapter_id):
                outcomes.append(self._unknown(adapter.adapter_id, "returned a finding outside review context"))
                continue
            persisted = tuple(self._store.record(finding) for finding in outcome.findings)
            normalized = replace(outcome, findings=persisted)
            outcomes.append(normalized)
            recorded.extend(persisted)
        verdict = self._aggregate_verdict(outcomes)
        return EngineeringReviewReport(
            request=request,
            verdict=verdict,
            outcomes=tuple(outcomes),
            findings=tuple(recorded),
        )

    @staticmethod
    def _unknown(adapter_id: str, reason: str) -> ReviewOutcome:
        return ReviewOutcome(
            adapter_id=adapter_id,
            verdict=Verdict.UNKNOWN,
            reason=f"adapter {adapter_id} {reason}",
        )

    @staticmethod
    def _findings_match_request(
        findings: tuple[EngineeringFinding, ...],
        request: EngineeringReviewRequest,
        adapter_id: str,
    ) -> bool:
        return all(
            finding.run_id == request.run_id
            and finding.task_id == request.task_id
            and finding.repository == request.repository
            and finding.base_revision == request.base_revision
            and finding.candidate_revision == request.candidate_revision
            and finding.source == adapter_id
            for finding in findings
        )

    @staticmethod
    def _aggregate_verdict(outcomes: list[ReviewOutcome]) -> Verdict:
        verdicts = {outcome.verdict for outcome in outcomes}
        if Verdict.FAIL in verdicts:
            return Verdict.FAIL
        if Verdict.UNKNOWN in verdicts:
            return Verdict.UNKNOWN
        return Verdict.PASS
