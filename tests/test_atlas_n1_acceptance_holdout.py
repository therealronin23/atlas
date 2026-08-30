"""WP-EH-HOLDOUT: protected holdout and evaluator-isolation fixtures."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    HOLDOUT_RETENTION_METADATA,
    CandidateHoldoutRequest,
    CandidateIdentityMismatchError,
    EvaluatorIsolationPolicy,
    HoldoutCandidateSurface,
    HoldoutContaminationChecker,
    HoldoutContaminationFinding,
    HoldoutContaminationKind,
    HoldoutProvenance,
    ProtectedHoldoutAccessBoundary,
    ProtectedHoldoutFixture,
)


def _provenance(**updates: object) -> HoldoutProvenance:
    payload: dict[str, object] = {
        "corpus_class_id": "CORPUS-HOLDOUT",
        "corpus_version": "CORPUS-HOLDOUT:sha256:fixture-v1",
        "content_sha256": "a" * 64,
        "source_canon_ids": ("CR-P00-001",),
        "creator_identity": "evaluator-001",
        "import_source": "local-synthetic-fixture",
        "generation_method": "SYNTHETIC_BOUNDED_FIXTURE",
        "contamination_history": (),
        "retention_metadata": HOLDOUT_RETENTION_METADATA,
        "supersedes_corpus_version": None,
        "supersedes_content_sha256": None,
    }
    payload.update(updates)
    return HoldoutProvenance.model_validate(payload)


def _holdout(**updates: object) -> ProtectedHoldoutFixture:
    payload: dict[str, object] = {
        "holdout_id": "holdout-001",
        "provenance": _provenance(),
    }
    payload.update(updates)
    return ProtectedHoldoutFixture.model_validate(payload)


def _policy(**updates: object) -> EvaluatorIsolationPolicy:
    payload: dict[str, object] = {
        "policy_id": "holdout-policy-001",
        "candidate_identity": "candidate-001",
        "evaluator_identity": "evaluator-001",
        "evaluator_criteria_owner_identity": "evaluator-001",
        "evaluator_verdict_state_owner_identity": "evaluator-001",
        "candidate_visibility": "DENIED",
        "candidate_can_train_or_tune_on_holdout": False,
        "candidate_can_select_or_mutate_evaluator_subsets": False,
        "candidate_can_write_evaluator_criteria": False,
        "candidate_can_write_evaluator_verdict_state": False,
    }
    payload.update(updates)
    return EvaluatorIsolationPolicy.model_validate(payload)


def _request(
    surface: HoldoutCandidateSurface = HoldoutCandidateSurface.INSPECT_HOLDOUT,
    **updates: object,
) -> CandidateHoldoutRequest:
    payload: dict[str, object] = {
        "request_id": "candidate-request-001",
        "candidate_identity": "candidate-001",
        "requested_surface": surface,
    }
    payload.update(updates)
    return CandidateHoldoutRequest.model_validate(payload)


@pytest.mark.parametrize("surface", tuple(HoldoutCandidateSurface))
def test_candidate_receives_only_a_denial_for_every_protected_surface(
    surface: HoldoutCandidateSurface,
) -> None:
    boundary = ProtectedHoldoutAccessBoundary(_policy(), _holdout())

    denial = boundary.deny_candidate_access(_request(surface))

    assert denial.request_id == "candidate-request-001"
    assert denial.candidate_identity == "candidate-001"
    assert denial.requested_surface is surface
    assert denial.candidate_visibility == "DENIED"
    assert denial.access_granted is False
    assert set(type(denial).model_fields) == {
        "request_id",
        "candidate_identity",
        "requested_surface",
        "candidate_visibility",
        "access_granted",
    }


def test_candidate_identity_must_match_the_frozen_isolation_policy() -> None:
    boundary = ProtectedHoldoutAccessBoundary(_policy(), _holdout())

    with pytest.raises(CandidateIdentityMismatchError, match="candidate-001"):
        boundary.deny_candidate_access(_request(candidate_identity="candidate-002"))


def test_policy_rejects_candidate_evaluator_identity_collision() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        _policy(evaluator_identity="candidate-001")


@pytest.mark.parametrize(
    "field_name",
    (
        "candidate_can_train_or_tune_on_holdout",
        "candidate_can_select_or_mutate_evaluator_subsets",
        "candidate_can_write_evaluator_criteria",
        "candidate_can_write_evaluator_verdict_state",
    ),
)
def test_policy_rejects_every_candidate_control_surface(field_name: str) -> None:
    with pytest.raises(ValidationError):
        _policy(**{field_name: True})


def test_boundary_revalidates_a_model_construct_policy_bypass_attempt() -> None:
    policy = _policy()
    forged = EvaluatorIsolationPolicy.model_construct(
        **{
            **policy.model_dump(),
            "candidate_can_write_evaluator_verdict_state": True,
        }
    )

    with pytest.raises(ValidationError):
        ProtectedHoldoutAccessBoundary(forged, _holdout())


def test_holdout_provenance_is_immutable_versioned_and_has_no_raw_case_payload(
) -> None:
    provenance = _provenance()

    assert provenance.corpus_class_id == "CORPUS-HOLDOUT"
    assert provenance.content_sha256 == "a" * 64
    assert provenance.retention_metadata == HOLDOUT_RETENTION_METADATA
    assert "raw_case_payload" not in type(provenance).model_fields
    with pytest.raises(ValidationError):
        provenance.corpus_version = "different-version"  # type: ignore[misc]


def test_corrected_holdout_version_requires_complete_supersession_provenance() -> None:
    with pytest.raises(ValidationError, match="both"):
        _provenance(supersedes_corpus_version="CORPUS-HOLDOUT:sha256:fixture-v0")
    with pytest.raises(ValidationError, match="differ"):
        _provenance(
            supersedes_corpus_version="CORPUS-HOLDOUT:sha256:fixture-v1",
            supersedes_content_sha256="b" * 64,
        )

    corrected = _provenance(
        corpus_version="CORPUS-HOLDOUT:sha256:fixture-v2",
        content_sha256="b" * 64,
        supersedes_corpus_version="CORPUS-HOLDOUT:sha256:fixture-v1",
        supersedes_content_sha256="a" * 64,
    )

    assert corrected.supersedes_corpus_version == (
        "CORPUS-HOLDOUT:sha256:fixture-v1"
    )
    assert corrected.supersedes_content_sha256 == "a" * 64


def test_direct_holdout_contamination_requires_revalidation_without_promotion(
) -> None:
    finding = HoldoutContaminationFinding(
        finding_id="finding-direct-exposure-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.CANDIDATE_TRAINING_OR_TUNING,
        evidence_reference="evidence:training-exposure-001",
    )

    assessment = HoldoutContaminationChecker().assess(_holdout(), (finding,))

    assert assessment.direct_candidate_exposure_detected is True
    assert assessment.public_familiarity_risk_recorded is False
    assert assessment.revalidation_required is True
    assert "result" not in type(assessment).model_fields


def test_public_or_upstream_familiarity_is_retained_as_risk_not_silently_ignored(
) -> None:
    finding = HoldoutContaminationFinding(
        finding_id="finding-public-familiarity-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.PUBLIC_OR_UPSTREAM_FAMILIARITY,
        evidence_reference="evidence:public-corpus-lineage-001",
    )

    assessment = HoldoutContaminationChecker().assess(_holdout(), (finding,))

    assert assessment.direct_candidate_exposure_detected is False
    assert assessment.public_familiarity_risk_recorded is True
    assert assessment.revalidation_required is False
    assert assessment.finding_ids == ("finding-public-familiarity-001",)


def test_contamination_assessment_preserves_input_order_and_rejects_cross_holdout(
) -> None:
    first = HoldoutContaminationFinding(
        finding_id="finding-first-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.PUBLIC_OR_UPSTREAM_FAMILIARITY,
        evidence_reference="evidence:first-001",
    )
    second = HoldoutContaminationFinding(
        finding_id="finding-second-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.CANDIDATE_EVALUATOR_SUBSET_MUTATION,
        evidence_reference="evidence:second-001",
    )

    assessment = HoldoutContaminationChecker().assess(_holdout(), (first, second))

    assert assessment.finding_ids == ("finding-first-001", "finding-second-001")
    assert assessment.revalidation_required is True

    mismatched = second.model_copy(update={"holdout_id": "holdout-002"})
    with pytest.raises(ValueError, match="holdout identity"):
        HoldoutContaminationChecker().assess(_holdout(), (mismatched,))


def test_holdout_boundary_and_assessment_have_no_authority_or_result_promotion_surface(
) -> None:
    boundary = ProtectedHoldoutAccessBoundary(_policy(), _holdout())
    assessment = HoldoutContaminationChecker().assess(_holdout(), ())

    assert not hasattr(boundary, "authorize")
    assert not hasattr(boundary, "promote")
    assert not hasattr(HoldoutContaminationChecker(), "authorize")
    assert not hasattr(HoldoutContaminationChecker(), "promote")
    assert "result" not in type(assessment).model_fields
