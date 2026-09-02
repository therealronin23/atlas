"""WP-EH-STATEOBS: read-only state and UNKNOWN_EFFECT observations."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance.core import TimestampOrder
from atlas.acceptance.state_observation import (
    ConflictingWriterProvenanceError,
    MissingUnknownEffectObservationError,
    SingleWriterProvenanceChecker,
    StateObservationAdapter,
    StateSnapshotEvidence,
    StateSubjectMismatchError,
    StateTransitionObservation,
    UnknownEffectDurabilityChecker,
    UnknownEffectObservation,
    UnknownEffectOrderError,
    UnknownEffectProvenanceDriftError,
)


def _order(
    sequence: int,
    *,
    timestamp: datetime | None = None,
    run_id: str = "run-stateobs-001",
) -> TimestampOrder:
    return TimestampOrder(
        timestamp=timestamp or datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        run_id=run_id,
        sequence=sequence,
    )


def _snapshot(
    version: str,
    hash_character: str,
    **updates: object,
) -> StateSnapshotEvidence:
    payload: dict[str, object] = {
        "state_subject_identity": "state-subject-001",
        "state_version": version,
        "state_sha256": hash_character * 64,
        "evidence_reference": f"evidence:{version}",
    }
    payload.update(updates)
    return StateSnapshotEvidence.model_validate(payload)


def _transition(
    observation_id: str = "transition-observation-001",
    *,
    sequence: int = 1,
    writer_identity: str = "state-writer-001",
    before_version: str = "state-v1",
    after_version: str = "state-v2",
) -> StateTransitionObservation:
    return StateTransitionObservation(
        observation_id=observation_id,
        before=_snapshot(before_version, "a"),
        after=_snapshot(after_version, "b"),
        observed_writer_identity=writer_identity,
        writer_receipt_reference=f"receipt:{observation_id}",
        timestamp_order=_order(sequence),
        harness_state_write_performed=False,
    )


def _unknown(
    observation_id: str = "unknown-effect-observation-001",
    *,
    observed_sequence: int = 1,
    first_sequence: int = 1,
    provenance_reference: str = "evidence:unknown-effect-001",
) -> UnknownEffectObservation:
    return UnknownEffectObservation(
        observation_id=observation_id,
        effect_identity="effect-unknown-001",
        state_subject_identity="state-subject-001",
        origin_transition_observation_id="transition-observation-001",
        provenance_reference=provenance_reference,
        first_observed_order=_order(first_sequence),
        observed_order=_order(observed_sequence),
        effect_state="UNKNOWN_EFFECT",
        harness_effect_resolution_performed=False,
    )


def test_transition_observation_is_strict_immutable_and_read_only() -> None:
    observation = StateObservationAdapter().observe_transition(_transition())

    assert observation.before.state_version == "state-v1"
    assert observation.after.state_version == "state-v2"
    assert observation.observed_writer_identity == "state-writer-001"
    assert observation.harness_state_write_performed is False
    with pytest.raises(ValidationError):
        observation.observed_writer_identity = "different"  # type: ignore[misc]


def test_transition_rejects_subject_substitution_and_non_transition() -> None:
    with pytest.raises(ValidationError, match="subject identity"):
        StateTransitionObservation(
            observation_id="transition-substitution-001",
            before=_snapshot("state-v1", "a"),
            after=_snapshot(
                "state-v2",
                "b",
                state_subject_identity="state-subject-002",
            ),
            observed_writer_identity="state-writer-001",
            writer_receipt_reference="receipt:transition-substitution-001",
            timestamp_order=_order(1),
        )

    with pytest.raises(ValidationError, match="version must differ"):
        StateTransitionObservation(
            observation_id="transition-noop-001",
            before=_snapshot("state-v1", "a"),
            after=_snapshot("state-v1", "b"),
            observed_writer_identity="state-writer-001",
            writer_receipt_reference="receipt:transition-noop-001",
            timestamp_order=_order(1),
        )


def test_adapter_revalidates_model_construct_state_write_bypass() -> None:
    observation = _transition()
    forged = StateTransitionObservation.model_construct(
        **{
            **observation.model_dump(),
            "harness_state_write_performed": True,
        }
    )

    with pytest.raises(ValidationError):
        StateObservationAdapter().observe_transition(forged)


def test_single_writer_provenance_preserves_complete_observation_order() -> None:
    first = _transition("transition-observation-001", sequence=1)
    second = _transition(
        "transition-observation-002",
        sequence=2,
        before_version="state-v2",
        after_version="state-v3",
    )

    assessment = SingleWriterProvenanceChecker().check(
        "state-subject-001",
        (first, second),
    )

    assert assessment.state_subject_identity == "state-subject-001"
    assert assessment.observation_ids == (
        "transition-observation-001",
        "transition-observation-002",
    )
    assert assessment.observed_writer_identity == "state-writer-001"
    assert assessment.provenance_consistent is True
    assert "result" not in type(assessment).model_fields


def test_single_writer_provenance_fails_closed_on_conflicting_writer() -> None:
    first = _transition("transition-observation-001", sequence=1)
    second = _transition(
        "transition-observation-002",
        sequence=2,
        writer_identity="state-writer-002",
        before_version="state-v2",
        after_version="state-v3",
    )

    with pytest.raises(ConflictingWriterProvenanceError, match="state-writer"):
        SingleWriterProvenanceChecker().check(
            "state-subject-001",
            (first, second),
        )


def test_single_writer_provenance_rejects_empty_or_cross_subject_trace() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SingleWriterProvenanceChecker().check("state-subject-001", ())

    mismatched = _transition().model_copy(
        update={
            "after": _snapshot(
                "state-v2",
                "b",
                state_subject_identity="state-subject-002",
            )
        }
    )
    with pytest.raises(ValidationError):
        SingleWriterProvenanceChecker().check("state-subject-001", (mismatched,))

    different_subject = _transition().model_copy(
        update={
            "before": _snapshot(
                "state-v1",
                "a",
                state_subject_identity="state-subject-002",
            ),
            "after": _snapshot(
                "state-v2",
                "b",
                state_subject_identity="state-subject-002",
            ),
        }
    )
    with pytest.raises(StateSubjectMismatchError, match="state-subject-001"):
        SingleWriterProvenanceChecker().check(
            "state-subject-001",
            (different_subject,),
        )


def test_unknown_effect_observation_preserves_exact_adverse_state() -> None:
    observation = StateObservationAdapter().observe_unknown_effect(_unknown())

    assert observation.effect_state == "UNKNOWN_EFFECT"
    assert observation.harness_effect_resolution_performed is False
    assert "result" not in type(observation).model_fields
    with pytest.raises(ValidationError):
        observation.effect_state = "KNOWN"  # type: ignore[misc]


def test_unknown_effect_durability_binds_identity_provenance_and_origin() -> None:
    previous = _unknown(observed_sequence=1)
    current = _unknown(
        "unknown-effect-observation-002",
        observed_sequence=2,
    )

    assessment = UnknownEffectDurabilityChecker().assert_retained(previous, current)

    assert assessment.effect_identity == "effect-unknown-001"
    assert assessment.previous_observation_id == "unknown-effect-observation-001"
    assert assessment.current_observation_id == "unknown-effect-observation-002"
    assert assessment.unknown_effect_preserved is True
    assert assessment.provenance_preserved is True


def test_unknown_effect_durability_rejects_disappearance() -> None:
    with pytest.raises(MissingUnknownEffectObservationError, match="disappeared"):
        UnknownEffectDurabilityChecker().assert_retained(_unknown(), None)


@pytest.mark.parametrize(
    "updates",
    (
        {"effect_identity": "effect-unknown-002"},
        {"state_subject_identity": "state-subject-002"},
        {"origin_transition_observation_id": "transition-observation-002"},
        {"provenance_reference": "evidence:changed"},
        {"first_observed_order": _order(0)},
    ),
)
def test_unknown_effect_durability_rejects_provenance_drift(
    updates: dict[str, object],
) -> None:
    previous = _unknown(observed_sequence=1)
    current = _unknown(
        "unknown-effect-observation-002",
        observed_sequence=2,
    ).model_copy(update=updates)

    with pytest.raises(UnknownEffectProvenanceDriftError):
        UnknownEffectDurabilityChecker().assert_retained(previous, current)


def test_unknown_effect_rejects_silent_resolution_and_order_regression() -> None:
    with pytest.raises(ValidationError):
        UnknownEffectObservation.model_validate(
            {
                **_unknown().model_dump(),
                "effect_state": "RESOLVED",
            }
        )

    previous = _unknown(observed_sequence=2)
    current = _unknown(
        "unknown-effect-observation-002",
        observed_sequence=1,
    )
    with pytest.raises(UnknownEffectOrderError, match="later"):
        UnknownEffectDurabilityChecker().assert_retained(previous, current)


def test_state_observation_seam_has_no_writer_authority_or_resolution_api() -> None:
    adapter = StateObservationAdapter()
    writer_checker = SingleWriterProvenanceChecker()
    effect_checker = UnknownEffectDurabilityChecker()

    for candidate in (adapter, writer_checker, effect_checker):
        assert not hasattr(candidate, "write")
        assert not hasattr(candidate, "persist")
        assert not hasattr(candidate, "authorize")
        assert not hasattr(candidate, "resolve")
