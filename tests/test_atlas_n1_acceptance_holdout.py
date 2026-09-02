"""WP-EH-HOLDOUT: protected holdout and evaluator-isolation fixtures."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.acceptance.holdout import (
    HOLDOUT_RETENTION_METADATA,
    CandidateHoldoutRequest,
    CandidateIdentityMismatchError,
    EvaluatorIsolationPolicy,
    HoldoutCandidateSurface,
    HoldoutContaminationAssessment,
    HoldoutContaminationChecker,
    HoldoutContaminationEpistemicState,
    HoldoutContaminationFinding,
    HoldoutContaminationKind,
    HoldoutInspectionStatus,
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


def _deny(
    *,
    policy: EvaluatorIsolationPolicy | None = None,
    holdout: ProtectedHoldoutFixture | None = None,
):
    return ProtectedHoldoutAccessBoundary(
        policy or _policy(),
        holdout or _holdout(),
    ).deny_candidate_access(_request())


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
    assert denial.holdout_id == "holdout-001"
    assert denial.policy_id == "holdout-policy-001"
    assert denial.evaluator_identity == "evaluator-001"
    assert len(denial.boundary_binding_sha256) == 64
    assert set(type(denial).model_fields) == {
        "request_id",
        "candidate_identity",
        "requested_surface",
        "holdout_id",
        "policy_id",
        "evaluator_identity",
        "boundary_binding_sha256",
        "candidate_visibility",
        "access_granted",
    }


def test_candidate_identity_must_match_the_isolation_policy() -> None:
    boundary = ProtectedHoldoutAccessBoundary(_policy(), _holdout())

    with pytest.raises(CandidateIdentityMismatchError, match="candidate-001"):
        boundary.deny_candidate_access(_request(candidate_identity="candidate-002"))


@pytest.mark.parametrize(
    ("policy_updates", "holdout_updates", "provenance_updates"),
    (
        ({}, {"holdout_id": "holdout-002"}, {}),
        ({"policy_id": "holdout-policy-002"}, {}, {}),
        (
            {
                "evaluator_identity": "evaluator-002",
                "evaluator_criteria_owner_identity": "evaluator-002",
                "evaluator_verdict_state_owner_identity": "evaluator-002",
            },
            {},
            {},
        ),
        ({}, {}, {"corpus_version": "CORPUS-HOLDOUT:sha256:fixture-v2"}),
        ({}, {}, {"content_sha256": "b" * 64}),
        ({}, {}, {"source_canon_ids": ("CR-P00-002",)}),
        ({}, {}, {"import_source": "different-local-fixture"}),
        ({}, {}, {"generation_method": "DIFFERENT_SYNTHETIC_METHOD"}),
        ({}, {}, {"contamination_history": ("evidence:history-001",)}),
    ),
)
def test_denial_is_bound_to_each_material_boundary_identity(
    policy_updates: dict[str, object],
    holdout_updates: dict[str, object],
    provenance_updates: dict[str, object],
) -> None:
    baseline = _deny()
    substituted_holdout = _holdout(
        provenance=_provenance(**provenance_updates),
        **holdout_updates,
    )
    substituted = _deny(
        policy=_policy(**policy_updates),
        holdout=substituted_holdout,
    )

    assert substituted != baseline
    assert substituted.boundary_binding_sha256 != baseline.boundary_binding_sha256
    assert "raw_case_payload" not in substituted.model_dump()
    assert "criteria" not in substituted.model_dump()
    assert "verdict" not in substituted.model_dump()


def test_same_candidate_request_cannot_collapse_distinct_boundaries() -> None:
    first = _deny()
    substituted = _deny(
        policy=_policy(
            policy_id="holdout-policy-002",
            evaluator_identity="evaluator-002",
            evaluator_criteria_owner_identity="evaluator-002",
            evaluator_verdict_state_owner_identity="evaluator-002",
        ),
        holdout=_holdout(
            holdout_id="holdout-002",
            provenance=_provenance(
                corpus_version="CORPUS-HOLDOUT:sha256:fixture-v9",
                content_sha256="b" * 64,
                import_source="different-local-fixture",
            ),
        ),
    )

    assert first.request_id == substituted.request_id
    assert first.candidate_identity == substituted.candidate_identity
    assert first.requested_surface == substituted.requested_surface
    assert first.boundary_binding_sha256 != substituted.boundary_binding_sha256
    assert first != substituted


def test_boundary_binding_revalidates_model_construct_and_copy_bypasses() -> None:
    forged_policy = _policy().model_copy(update={"policy_id": ""})
    with pytest.raises(ValidationError):
        ProtectedHoldoutAccessBoundary(forged_policy, _holdout())

    forged_provenance = HoldoutProvenance.model_construct(
        **{**_provenance().model_dump(), "content_sha256": "not-a-sha"}
    )
    forged_holdout = _holdout().model_copy(update={"provenance": forged_provenance})
    with pytest.raises(ValidationError):
        ProtectedHoldoutAccessBoundary(_policy(), forged_holdout)


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


def test_holdout_provenance_is_immutable_versioned_and_has_no_case_payload() -> None:
    provenance = _provenance()

    assert provenance.corpus_class_id == "CORPUS-HOLDOUT"
    assert provenance.content_sha256 == "a" * 64
    assert provenance.retention_metadata == HOLDOUT_RETENTION_METADATA
    assert "raw_case_payload" not in type(provenance).model_fields
    with pytest.raises(ValidationError):
        provenance.corpus_version = "different-version"  # type: ignore[misc]


def test_corrected_holdout_requires_complete_supersession_provenance() -> None:
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


def test_direct_contamination_requires_revalidation_without_promotion() -> None:
    finding = HoldoutContaminationFinding(
        finding_id="finding-direct-exposure-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.CANDIDATE_TRAINING_OR_TUNING,
        evidence_reference="evidence:training-exposure-001",
    )

    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (finding,),
        inspection_status=HoldoutInspectionStatus.INSPECTED,
    )

    assert assessment.direct_candidate_exposure_detected is True
    assert assessment.public_familiarity_risk_recorded is False
    assert assessment.revalidation_required is True
    assert assessment.epistemic_state is (
        HoldoutContaminationEpistemicState.KNOWN_CONTAMINATED
    )
    assert "result" not in type(assessment).model_fields


def test_public_familiarity_is_retained_as_risk_not_silently_ignored() -> None:
    finding = HoldoutContaminationFinding(
        finding_id="finding-public-familiarity-001",
        holdout_id="holdout-001",
        kind=HoldoutContaminationKind.PUBLIC_OR_UPSTREAM_FAMILIARITY,
        evidence_reference="evidence:public-corpus-lineage-001",
    )

    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (finding,),
        inspection_status=HoldoutInspectionStatus.INSPECTED,
    )

    assert assessment.direct_candidate_exposure_detected is False
    assert assessment.public_familiarity_risk_recorded is True
    assert assessment.revalidation_required is False
    assert assessment.finding_ids == ("finding-public-familiarity-001",)


def test_historical_contamination_without_new_findings_is_not_clean() -> None:
    contaminated = _holdout(
        provenance=_provenance(
            contamination_history=("evidence:historical-contamination-001",)
        )
    )

    assessment = HoldoutContaminationChecker().assess(
        contaminated,
        (),
        inspection_status=HoldoutInspectionStatus.NOT_INSPECTED,
    )

    assert assessment.epistemic_state is (
        HoldoutContaminationEpistemicState.KNOWN_CONTAMINATED
    )
    assert assessment.contamination_history == (
        "evidence:historical-contamination-001",
    )
    assert assessment.finding_ids == ()
    assert assessment.direct_candidate_exposure_detected is None
    assert assessment.public_familiarity_risk_recorded is None
    assert assessment.revalidation_required is None


@pytest.mark.parametrize(
    "inspection_status",
    (
        HoldoutInspectionStatus.NOT_INSPECTED,
        HoldoutInspectionStatus.INCOMPLETE,
        HoldoutInspectionStatus.UNRESOLVED,
    ),
)
def test_unresolved_inspection_remains_unknown(
    inspection_status: HoldoutInspectionStatus,
) -> None:
    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (),
        inspection_status=inspection_status,
    )

    assert assessment.epistemic_state is HoldoutContaminationEpistemicState.UNKNOWN
    assert assessment.direct_candidate_exposure_detected is None
    assert assessment.public_familiarity_risk_recorded is None
    assert assessment.revalidation_required is None


def test_complete_inspection_can_record_evidence_backed_clear_state() -> None:
    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (),
        inspection_status=HoldoutInspectionStatus.INSPECTED,
    )

    assert assessment.epistemic_state is (
        HoldoutContaminationEpistemicState.KNOWN_CLEAR
    )
    assert assessment.contamination_history == ()
    assert assessment.finding_ids == ()
    assert assessment.direct_candidate_exposure_detected is False
    assert assessment.public_familiarity_risk_recorded is False
    assert assessment.revalidation_required is False


def test_inspection_status_is_required_instead_of_defaulting_empty_to_clean() -> None:
    with pytest.raises(TypeError):
        HoldoutContaminationChecker().assess(_holdout(), ())  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "updates",
    (
        {"epistemic_state": HoldoutContaminationEpistemicState.UNKNOWN},
        {
            "contamination_history": ("evidence:historical-contamination-001",),
        },
        {
            "finding_ids": ("finding-direct-001",),
            "finding_kinds": (
                HoldoutContaminationKind.CANDIDATE_TRAINING_OR_TUNING,
            ),
        },
        {
            "inspection_status": HoldoutInspectionStatus.NOT_INSPECTED,
            "epistemic_state": HoldoutContaminationEpistemicState.UNKNOWN,
        },
    ),
)
def test_forged_epistemic_combinations_fail_closed(
    updates: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "holdout_id": "holdout-001",
        "inspection_status": HoldoutInspectionStatus.INSPECTED,
        "epistemic_state": HoldoutContaminationEpistemicState.KNOWN_CLEAR,
        "finding_ids": (),
        "finding_kinds": (),
        "contamination_history": (),
        "direct_candidate_exposure_detected": False,
        "public_familiarity_risk_recorded": False,
        "revalidation_required": False,
    }
    payload.update(updates)

    with pytest.raises(ValidationError, match="epistemic|derived|inspection"):
        HoldoutContaminationAssessment.model_validate(payload)


def test_contamination_preserves_input_order_and_rejects_cross_holdout() -> None:
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

    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (first, second),
        inspection_status=HoldoutInspectionStatus.INSPECTED,
    )

    assert assessment.finding_ids == ("finding-first-001", "finding-second-001")
    assert assessment.revalidation_required is True

    mismatched = second.model_copy(update={"holdout_id": "holdout-002"})
    with pytest.raises(ValueError, match="holdout identity"):
        HoldoutContaminationChecker().assess(
            _holdout(),
            (mismatched,),
            inspection_status=HoldoutInspectionStatus.INSPECTED,
        )


def test_boundary_exposes_no_holdout_authority_or_result_promotion_surface() -> None:
    boundary = ProtectedHoldoutAccessBoundary(_policy(), _holdout())
    assessment = HoldoutContaminationChecker().assess(
        _holdout(),
        (),
        inspection_status=HoldoutInspectionStatus.INSPECTED,
    )

    assert ProtectedHoldoutAccessBoundary.__slots__ == (
        "_candidate_identity",
        "_holdout_id",
        "_policy_id",
        "_evaluator_identity",
        "_boundary_binding_sha256",
    )
    assert not hasattr(boundary, "holdout")
    assert not hasattr(boundary, "authorize")
    assert not hasattr(boundary, "promote")
    assert not hasattr(HoldoutContaminationChecker(), "authorize")
    assert not hasattr(HoldoutContaminationChecker(), "promote")
    assert "result" not in type(assessment).model_fields
