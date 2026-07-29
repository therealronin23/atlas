"""Tests for explicit-acceptance review baselines.

An all-green review is evidence, not an implicit promotion.  Only a caller that
supplies an acceptance reference may persist a baseline for later incremental
diff selection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.verify import Verdict
from atlas.engineering.baselines import (
    EngineeringReviewBaselineStore,
    ReviewBaselineSource,
)
from atlas.engineering.findings import (
    EngineeringFinding,
    FindingEvidence,
    FindingSeverity,
    FindingStatus,
)
from atlas.engineering.review import (
    EngineeringReviewReport,
    EngineeringReviewRequest,
    ReviewOutcome,
)
from atlas.events.schemas import Risk


def _request(*, base: str = "a" * 40, candidate: str = "b" * 40) -> EngineeringReviewRequest:
    return EngineeringReviewRequest(
        run_id="run_baseline_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision=base,
        candidate_revision=candidate,
        diff="caller supplies the bounded diff after selection",
        scope=("src/atlas/example.py",),
        acceptance_criteria=("Review only the selected delta.",),
        at="2026-07-29T15:00:00+00:00",
    )


def _report(*, verdict: Verdict = Verdict.PASS) -> EngineeringReviewReport:
    return EngineeringReviewReport(
        request=_request(),
        verdict=verdict,
        outcomes=(ReviewOutcome(adapter_id="deterministic", verdict=verdict),),
        findings=(),
    )


def _resolved_finding() -> EngineeringFinding:
    return EngineeringFinding(
        id="finding_baseline_001",
        run_id="run_baseline_001",
        task_id="task_001",
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        source="deterministic",
        category="review",
        severity=FindingSeverity.MINOR,
        status=FindingStatus.RESOLVED,
        summary="Resolved before acceptance",
        detail="The prior finding is evidence only.",
        locations=(),
        evidence=(FindingEvidence(kind="test", reference="prior"),),
        reproduction=None,
        suggested_action=None,
        patch_ref=None,
        dedupe_key="prior-key",
        created_at="2026-07-29T14:00:00+00:00",
        updated_at="2026-07-29T15:00:00+00:00",
        risk=Risk.LOW,
    )


def test_explicit_acceptance_becomes_the_next_incremental_base_and_preserves_state(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baseline = store.record_accepted(
        _report(),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T15:01:00+00:00",
        finding_snapshot=(_resolved_finding(),),
    )

    selection = store.select(_request(base="a" * 40, candidate="c" * 40))

    assert baseline.revision == "b" * 40
    assert baseline.finding_state[0].finding_id == "finding_baseline_001"
    assert baseline.finding_state[0].status is FindingStatus.RESOLVED
    assert selection.source is ReviewBaselineSource.ACCEPTED_BASELINE
    assert selection.base_revision == "b" * 40
    assert selection.accepted_baseline == baseline
    assert selection.prior_finding_state == baseline.finding_state
    assert selection.review_required is True
    assert selection.requires_ancestry_verification is True


def test_pass_does_not_become_a_baseline_without_an_explicit_acceptance_reference(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")

    with pytest.raises(ValueError, match="acceptance_ref"):
        store.record_accepted(
            _report(),
            acceptance_ref="",
            accepted_by="operator",
            at="2026-07-29T15:01:00+00:00",
        )

    assert store.count() == 0


def test_failed_or_unknown_review_cannot_be_accepted_as_a_baseline(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")

    for verdict in (Verdict.FAIL, Verdict.UNKNOWN):
        with pytest.raises(ValueError, match="PASS"):
            store.record_accepted(
                _report(verdict=verdict),
                acceptance_ref="approval_001",
                accepted_by="operator",
                at="2026-07-29T15:01:00+00:00",
            )

    assert store.count() == 0


def test_empty_pass_report_cannot_be_accepted_as_a_baseline(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    empty_report = EngineeringReviewReport(
        request=_request(),
        verdict=Verdict.PASS,
        outcomes=(),
        findings=(),
    )

    with pytest.raises(ValueError, match="at least one"):
        store.record_accepted(
            empty_report,
            acceptance_ref="approval_001",
            accepted_by="operator",
            at="2026-07-29T15:01:00+00:00",
        )


def test_same_accepted_candidate_is_idempotent_and_does_not_require_a_new_review(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    first = store.record_accepted(
        _report(),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T15:01:00+00:00",
    )
    repeated = store.record_accepted(
        _report(),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T15:02:00+00:00",
    )

    selection = store.select(_request())

    assert repeated == first
    assert store.count() == 1
    assert selection.source is ReviewBaselineSource.ALREADY_ACCEPTED
    assert selection.review_required is False
    assert selection.base_revision == "b" * 40
    assert selection.requires_ancestry_verification is False


def test_cross_context_finding_snapshot_is_rejected(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    foreign = _resolved_finding().model_copy(update={"repository": "other-repository"})

    with pytest.raises(ValueError, match="finding snapshot"):
        store.record_accepted(
            _report(),
            acceptance_ref="approval_001",
            accepted_by="operator",
            at="2026-07-29T15:01:00+00:00",
            finding_snapshot=(foreign,),
        )


def test_without_an_accepted_baseline_selection_preserves_the_requested_base(tmp_path: Path) -> None:
    store = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")

    selection = store.select(_request(base="a" * 40, candidate="c" * 40))

    assert selection.source is ReviewBaselineSource.REQUESTED_BASE
    assert selection.base_revision == "a" * 40
    assert selection.accepted_baseline is None
    assert selection.prior_finding_state == ()
    assert selection.review_required is True
    assert selection.requires_ancestry_verification is True
