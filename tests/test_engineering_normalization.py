"""Tests for conservative incremental EngineeringFinding comparison.

The normalizer is deliberately observational: a finding missing from a later
review is not a resolution and no journal is changed as a side effect.
"""

from __future__ import annotations

import pytest

from atlas.core.verify import Verdict
from atlas.engineering.baselines import (
    BaselineFindingState,
    IncrementalReviewSelection,
    ReviewBaselineSource,
)
from atlas.engineering.findings import (
    EngineeringFinding,
    FindingEvidence,
    FindingSeverity,
    FindingStatus,
)
from atlas.engineering.normalization import (
    EngineeringIncrementalFindingNormalizer,
    IncrementalFindingRelationStatus,
)
from atlas.engineering.review import EngineeringReviewReport, EngineeringReviewRequest, ReviewOutcome
from atlas.events.schemas import Risk


def _request() -> EngineeringReviewRequest:
    return EngineeringReviewRequest(
        run_id="run_normalization_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        diff="verified delta",
        scope=("src/atlas/example.py",),
        acceptance_criteria=("Do not infer a lifecycle transition.",),
        at="2026-07-29T17:00:00+00:00",
    )


def _finding(*, finding_id: str, dedupe_key: str, status: FindingStatus) -> EngineeringFinding:
    request = _request()
    return EngineeringFinding(
        id=finding_id,
        run_id=request.run_id,
        task_id=request.task_id,
        repository=request.repository,
        base_revision=request.base_revision,
        candidate_revision=request.candidate_revision,
        source="deterministic",
        category="review",
        severity=FindingSeverity.MAJOR,
        status=status,
        summary="A bounded finding",
        detail="Evidence remains with its producer.",
        locations=(),
        evidence=(FindingEvidence(kind="test", reference="evidence"),),
        reproduction=None,
        suggested_action=None,
        patch_ref=None,
        dedupe_key=dedupe_key,
        created_at=request.at,
        updated_at=request.at,
        risk=Risk.MEDIUM,
    )


def _selection(*states: BaselineFindingState) -> IncrementalReviewSelection:
    return IncrementalReviewSelection(
        source=ReviewBaselineSource.ACCEPTED_BASELINE,
        base_revision="a" * 40,
        accepted_baseline=None,
        prior_finding_state=states,
        review_required=True,
    )


def _report(*findings: EngineeringFinding) -> EngineeringReviewReport:
    return EngineeringReviewReport(
        request=_request(),
        verdict=Verdict.FAIL if findings else Verdict.PASS,
        outcomes=(ReviewOutcome(adapter_id="deterministic", verdict=Verdict.PASS),),
        findings=findings,
    )


def test_normalizer_compares_only_exact_opaque_dedupe_keys() -> None:
    prior = BaselineFindingState(
        finding_id="finding_prior_001",
        dedupe_key="stable-key",
        status=FindingStatus.ACKNOWLEDGED,
        updated_at="2026-07-29T16:00:00+00:00",
    )
    current = _finding(
        finding_id="finding_current_001",
        dedupe_key="stable-key",
        status=FindingStatus.OPEN,
    )
    new = _finding(
        finding_id="finding_current_002",
        dedupe_key="new-key",
        status=FindingStatus.OPEN,
    )

    normalization = EngineeringIncrementalFindingNormalizer().normalize(
        report=_report(current, new),
        selection=_selection(prior),
    )

    assert [relation.status for relation in normalization.relations] == [
        IncrementalFindingRelationStatus.NEW,
        IncrementalFindingRelationStatus.REOBSERVED,
    ]
    reobserved = next(
        relation
        for relation in normalization.relations
        if relation.status is IncrementalFindingRelationStatus.REOBSERVED
    )
    assert reobserved.prior == prior
    assert reobserved.current == current


def test_missing_finding_is_not_automatically_resolved() -> None:
    prior = BaselineFindingState(
        finding_id="finding_prior_001",
        dedupe_key="prior-key",
        status=FindingStatus.OPEN,
        updated_at="2026-07-29T16:00:00+00:00",
    )

    normalization = EngineeringIncrementalFindingNormalizer().normalize(
        report=_report(),
        selection=_selection(prior),
    )

    relation = normalization.relations[0]
    assert relation.status is IncrementalFindingRelationStatus.NOT_REOBSERVED
    assert relation.prior == prior
    assert relation.current is None
    assert relation.prior.status is FindingStatus.OPEN


def test_normalizer_rejects_ambiguous_current_dedupe_keys() -> None:
    first = _finding(
        finding_id="finding_current_001",
        dedupe_key="duplicate-key",
        status=FindingStatus.OPEN,
    )
    second = _finding(
        finding_id="finding_current_002",
        dedupe_key="duplicate-key",
        status=FindingStatus.OPEN,
    )

    with pytest.raises(ValueError, match="duplicate current finding dedupe_key"):
        EngineeringIncrementalFindingNormalizer().normalize(
            report=_report(first, second),
            selection=_selection(),
        )


def test_normalizer_preserves_a_deduplicated_prior_journal_record() -> None:
    prior_run_record = _finding(
        finding_id="finding_prior_run_001",
        dedupe_key="stable-key",
        status=FindingStatus.OPEN,
    ).model_copy(update={"run_id": "run_prior_001", "task_id": "task_prior_001"})

    normalization = EngineeringIncrementalFindingNormalizer().normalize(
        report=_report(prior_run_record),
        selection=_selection(),
    )

    assert normalization.relations[0].status is IncrementalFindingRelationStatus.NEW
    assert normalization.relations[0].current == prior_run_record
