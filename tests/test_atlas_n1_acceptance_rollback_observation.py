"""WP-EH-ROLLBACK: rollback eligibility and reversal evidence only."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance.core import TimestampOrder
from atlas.acceptance.rollback_observation import (
    ReversalEvidenceChecker,
    RollbackCheckpointEvidence,
    RollbackCheckpointMismatchError,
    RollbackEligibilityAssessment,
    RollbackEligibilityChecker,
    RollbackEligibilityPredicateEvidence,
    RollbackObservationAdapter,
    RollbackReversalObservation,
    RollbackStateEvidence,
)


def _order(sequence: int) -> TimestampOrder:
    return TimestampOrder(
        timestamp=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc),
        run_id="run-rollback-001",
        sequence=sequence,
    )


def _checkpoint(**updates: object) -> RollbackCheckpointEvidence:
    payload: dict[str, object] = {
        "checkpoint_id": "checkpoint-001",
        "state_subject_identity": "state-subject-001",
        "state_version": "state-v1",
        "state_sha256": "a" * 64,
        "provenance_reference": "evidence:checkpoint-001",
        "observed_writer_identity": "state-writer-001",
        "timestamp_order": _order(1),
    }
    payload.update(updates)
    return RollbackCheckpointEvidence.model_validate(payload)


def _predicate(
    predicate_id: str,
    satisfied: bool,
) -> RollbackEligibilityPredicateEvidence:
    return RollbackEligibilityPredicateEvidence(
        predicate_id=predicate_id,
        satisfied=satisfied,
        evidence_reference=f"evidence:{predicate_id}",
    )


def _state(
    version: str,
    hash_character: str,
    **updates: object,
) -> RollbackStateEvidence:
    payload: dict[str, object] = {
        "state_subject_identity": "state-subject-001",
        "state_version": version,
        "state_sha256": hash_character * 64,
        "evidence_reference": f"evidence:{version}",
    }
    payload.update(updates)
    return RollbackStateEvidence.model_validate(payload)


def _reversal(**updates: object) -> RollbackReversalObservation:
    payload: dict[str, object] = {
        "observation_id": "reversal-observation-001",
        "checkpoint": _checkpoint(),
        "pre_reversal_state": _state("state-v2", "b"),
        "restored_state": _state("state-v3", "a"),
        "restored_checkpoint_id": "checkpoint-001",
        "reversal_evidence_reference": "evidence:reversal-observation-001",
        "timestamp_order": _order(2),
        "harness_rollback_performed": False,
        "harness_state_write_performed": False,
        "harness_deletion_performed": False,
    }
    payload.update(updates)
    return RollbackReversalObservation.model_validate(payload)


def test_checkpoint_identity_and_provenance_are_strict_and_immutable() -> None:
    checkpoint = _checkpoint()

    assert checkpoint.checkpoint_id == "checkpoint-001"
    assert checkpoint.state_sha256 == "a" * 64
    assert checkpoint.provenance_reference == "evidence:checkpoint-001"
    with pytest.raises(ValidationError):
        checkpoint.state_sha256 = "b" * 64  # type: ignore[misc]


def test_eligibility_uses_complete_explicit_predicate_trace() -> None:
    predicates = (
        _predicate("predicate-checkpoint-present", True),
        _predicate("predicate-reversal-evidence-available", True),
    )

    assessment = RollbackEligibilityChecker().assess(_checkpoint(), predicates)

    assert assessment.checkpoint.checkpoint_id == "checkpoint-001"
    assert tuple(item.predicate_id for item in assessment.predicate_trace) == (
        "predicate-checkpoint-present",
        "predicate-reversal-evidence-available",
    )
    assert assessment.eligible is True
    assert assessment.harness_rollback_performed is False
    assert "result" not in type(assessment).model_fields


def test_unsatisfied_predicate_remains_ineligible_without_normalization() -> None:
    predicates = (
        _predicate("predicate-checkpoint-present", True),
        _predicate("predicate-reversal-evidence-available", False),
    )

    assessment = RollbackEligibilityChecker().assess(_checkpoint(), predicates)

    assert assessment.eligible is False
    assert assessment.predicate_trace[1].satisfied is False


def test_eligibility_rejects_empty_duplicate_or_non_boolean_predicates() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RollbackEligibilityChecker().assess(_checkpoint(), ())

    duplicate = _predicate("predicate-duplicate", True)
    with pytest.raises(ValueError, match="identities must be unique"):
        RollbackEligibilityChecker().assess(_checkpoint(), (duplicate, duplicate))

    with pytest.raises(ValidationError):
        RollbackEligibilityPredicateEvidence.model_validate(
            {
                "predicate_id": "predicate-nonstrict",
                "satisfied": "true",
                "evidence_reference": "evidence:predicate-nonstrict",
            }
        )


def test_eligibility_assessment_rejects_forged_positive_decision() -> None:
    assessment = RollbackEligibilityChecker().assess(
        _checkpoint(),
        (_predicate("predicate-blocked", False),),
    )
    forged = RollbackEligibilityAssessment.model_construct(
        **{
            **assessment.model_dump(),
            "eligible": True,
        }
    )

    with pytest.raises(ValidationError, match="derived"):
        RollbackEligibilityAssessment.model_validate(forged)


def test_reversal_evidence_binds_exact_checkpoint_and_restored_content() -> None:
    observation = RollbackObservationAdapter().observe_reversal(_reversal())
    assertion = ReversalEvidenceChecker().assert_matches_checkpoint(observation)

    assert assertion.checkpoint_id == "checkpoint-001"
    assert assertion.observation_id == "reversal-observation-001"
    assert assertion.checkpoint_identity_bound is True
    assert assertion.restored_content_bound is True
    assert observation.harness_rollback_performed is False
    assert observation.harness_state_write_performed is False
    assert observation.harness_deletion_performed is False


def test_reversal_rejects_cross_subject_or_checkpoint_substitution() -> None:
    with pytest.raises(ValidationError, match="state subject"):
        _reversal(
            restored_state=_state(
                "state-v3",
                "a",
                state_subject_identity="state-subject-002",
            )
        )

    with pytest.raises(ValidationError, match="checkpoint identity"):
        _reversal(restored_checkpoint_id="checkpoint-002")


def test_reversal_rejects_wrong_restored_hash_and_noop_claim() -> None:
    with pytest.raises(ValidationError, match="content hash"):
        _reversal(restored_state=_state("state-v3", "c"))

    with pytest.raises(ValidationError, match="differ"):
        _reversal(pre_reversal_state=_state("state-v2", "a"))


def test_reversal_rejects_observation_before_checkpoint() -> None:
    with pytest.raises(ValidationError, match="later"):
        _reversal(timestamp_order=_order(0))


def test_adapter_revalidates_model_construct_effect_bypasses() -> None:
    observation = _reversal()
    forged = RollbackReversalObservation.model_construct(
        **{
            **observation.model_dump(),
            "harness_rollback_performed": True,
            "harness_state_write_performed": True,
            "harness_deletion_performed": True,
        }
    )

    with pytest.raises(ValidationError):
        RollbackObservationAdapter().observe_reversal(forged)


def test_reversal_checker_revalidates_forged_checkpoint_binding() -> None:
    observation = _reversal()
    forged = observation.model_copy(update={"restored_checkpoint_id": "checkpoint-002"})

    with pytest.raises(RollbackCheckpointMismatchError):
        ReversalEvidenceChecker().assert_matches_checkpoint(forged)


def test_rollback_seam_has_no_execute_delete_authorize_or_migrate_api() -> None:
    candidates = (
        RollbackEligibilityChecker(),
        RollbackObservationAdapter(),
        ReversalEvidenceChecker(),
    )
    for candidate in candidates:
        assert not hasattr(candidate, "execute")
        assert not hasattr(candidate, "rollback")
        assert not hasattr(candidate, "write")
        assert not hasattr(candidate, "delete")
        assert not hasattr(candidate, "authorize")
        assert not hasattr(candidate, "persist")
        assert not hasattr(candidate, "migrate")
