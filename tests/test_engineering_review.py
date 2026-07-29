"""Tests for the deterministic EngineeringFinding review composition.

These tests prevent a coordinator from inventing a second verifier, treating a
reviewer crash as a pass, or persisting an adapter finding for a different
repository/revision than the review it was asked to perform.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    UniversalVerifier,
    Verdict,
)
from atlas.engineering.findings import (
    EngineeringFinding,
    EngineeringFindingStore,
    FindingEvidence,
    FindingSeverity,
    FindingStatus,
)
from atlas.engineering.review import (
    EngineeringReviewCoordinator,
    EngineeringReviewRequest,
    ReviewOutcome,
    UniversalVerifierReviewAdapter,
)


@dataclass
class _FailingPatchVerifier:
    verifier_id: str = "diff_scope"
    cost: CostTier = CostTier.STATIC

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.PATCH

    def verify(self, artifact: Artifact) -> Evidence:
        return Evidence(
            verdict=Verdict.FAIL,
            checks=(Check(name="diff_scope", passed=False, detail="path outside scope", cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="path outside scope",
        )


@dataclass
class _PassingPatchVerifier:
    verifier_id: str = "diff_shape"
    cost: CostTier = CostTier.STATIC

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.PATCH

    def verify(self, artifact: Artifact) -> Evidence:
        return Evidence(
            verdict=Verdict.PASS,
            checks=(Check(name="diff_shape", passed=True, cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
        )


class _BrokenAdapter:
    adapter_id = "broken_reviewer"

    def review(self, request: EngineeringReviewRequest) -> ReviewOutcome:
        raise RuntimeError("do not expose this reviewer detail")


class _ForeignFindingAdapter:
    adapter_id = "foreign_reviewer"

    def review(self, request: EngineeringReviewRequest) -> ReviewOutcome:
        finding = EngineeringFinding(
            id="finding_foreign_001",
            run_id=request.run_id,
            task_id=request.task_id,
            repository="different-repository",
            base_revision=request.base_revision,
            candidate_revision=request.candidate_revision,
            source=self.adapter_id,
            category="review",
            severity=FindingSeverity.MAJOR,
            status=FindingStatus.OPEN,
            summary="wrong repository",
            detail="This adapter attempted to cross the review boundary.",
            locations=(),
            evidence=(FindingEvidence(kind="adapter", reference=self.adapter_id),),
            reproduction=None,
            suggested_action=None,
            patch_ref=None,
            dedupe_key="foreign",
            created_at=request.at,
            updated_at=request.at,
        )
        return ReviewOutcome(adapter_id=self.adapter_id, verdict=Verdict.FAIL, findings=(finding,))


def _request() -> EngineeringReviewRequest:
    return EngineeringReviewRequest(
        run_id="run_review_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        diff="--- a/src/atlas/core/example.py\n+++ b/src/atlas/core/example.py\n@@ -1 +1 @@\n-old = 1\n+old = 2\n",
        scope=("src/atlas/core/example.py",),
        acceptance_criteria=("Only the declared source file changes.",),
        at="2026-07-29T12:00:00+00:00",
    )


def test_universal_verifier_failure_becomes_one_deduplicated_finding(tmp_path: Path) -> None:
    adapter = UniversalVerifierReviewAdapter(
        adapter_id="universal_deterministic",
        verifier=UniversalVerifier([_FailingPatchVerifier()]),
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")
    coordinator = EngineeringReviewCoordinator(store=store, adapters=[adapter])

    first = coordinator.review(_request())
    repeated = coordinator.review(_request())

    assert first.verdict is Verdict.FAIL
    assert first.findings[0].source == "universal_deterministic"
    assert first.findings[0].severity is FindingSeverity.MAJOR
    assert repeated.findings[0].id == first.findings[0].id
    assert store.count() == 1


def test_universal_verifier_pass_produces_no_finding(tmp_path: Path) -> None:
    adapter = UniversalVerifierReviewAdapter(
        adapter_id="universal_deterministic",
        verifier=UniversalVerifier([_PassingPatchVerifier()]),
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringReviewCoordinator(store=store, adapters=[adapter]).review(_request())

    assert report.verdict is Verdict.PASS
    assert report.findings == ()
    assert store.count() == 0


def test_reviewer_exception_remains_unknown_and_does_not_persist_a_finding(tmp_path: Path) -> None:
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringReviewCoordinator(store=store, adapters=[_BrokenAdapter()]).review(_request())

    assert report.verdict is Verdict.UNKNOWN
    assert report.outcomes[0].verdict is Verdict.UNKNOWN
    assert report.outcomes[0].reason == "reviewer broken_reviewer failed with RuntimeError"
    assert store.count() == 0


def test_coordinator_rejects_finding_that_escapes_the_requested_repository(tmp_path: Path) -> None:
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringReviewCoordinator(store=store, adapters=[_ForeignFindingAdapter()]).review(_request())

    assert report.verdict is Verdict.UNKNOWN
    assert report.outcomes[0].reason == "adapter foreign_reviewer returned a finding outside review context"
    assert report.findings == ()
    assert store.count() == 0
