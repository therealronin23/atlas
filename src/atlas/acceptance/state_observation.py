"""WP-EH-STATEOBS: state/provenance observation without state ownership.

The seam revalidates immutable transition evidence, checks that an observed
subject has one writer identity in a supplied trace, and verifies that an
unresolved UNKNOWN_EFFECT observation remains durable. It does not write or
persist state, assign an owner, resolve an effect, or adjudicate acceptance.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, Self

from pydantic import model_validator

from atlas.acceptance.core import (
    TimestampOrder,
    _FrozenStrictModel,
    _NonEmptyText,
    _OpaqueId,
    _Sha256,
)


class StateSubjectMismatchError(ValueError):
    """Raised when evidence for another state subject enters a bounded trace."""


class ConflictingWriterProvenanceError(ValueError):
    """Raised when one subject has more than one observed writer identity."""


class MissingUnknownEffectObservationError(ValueError):
    """Raised when an unresolved effect disappears from later evidence."""


class UnknownEffectProvenanceDriftError(ValueError):
    """Raised when retained UNKNOWN_EFFECT evidence changes its binding."""


class UnknownEffectOrderError(ValueError):
    """Raised when a retained UNKNOWN_EFFECT observation is not later."""


class StateSnapshotEvidence(_FrozenStrictModel):
    """Content-bound evidence for one observed state version."""

    state_subject_identity: _OpaqueId
    state_version: _OpaqueId
    state_sha256: _Sha256
    evidence_reference: _NonEmptyText


class StateTransitionObservation(_FrozenStrictModel):
    """Read-only before/after evidence attributed to an observed writer."""

    observation_id: _OpaqueId
    before: StateSnapshotEvidence
    after: StateSnapshotEvidence
    observed_writer_identity: _OpaqueId
    writer_receipt_reference: _NonEmptyText
    timestamp_order: TimestampOrder
    harness_state_write_performed: Literal[False] = False

    @model_validator(mode="after")
    def _require_one_subject_and_distinct_versions(self) -> Self:
        before = StateSnapshotEvidence.model_validate(self.before)
        after = StateSnapshotEvidence.model_validate(self.after)
        if before.state_subject_identity != after.state_subject_identity:
            raise ValueError(
                "before and after state subject identity must match"
            )
        if before.state_version == after.state_version:
            raise ValueError("after state version must differ from before version")
        return self


class SingleWriterProvenanceAssessment(_FrozenStrictModel):
    """Complete observed trace with one writer identity, not ownership."""

    state_subject_identity: _OpaqueId
    observation_ids: tuple[_OpaqueId, ...]
    observed_writer_identity: _OpaqueId
    provenance_consistent: Literal[True] = True


class UnknownEffectObservation(_FrozenStrictModel):
    """An unresolved effect retained with stable origin and provenance."""

    observation_id: _OpaqueId
    effect_identity: _OpaqueId
    state_subject_identity: _OpaqueId
    origin_transition_observation_id: _OpaqueId
    provenance_reference: _NonEmptyText
    first_observed_order: TimestampOrder
    observed_order: TimestampOrder
    effect_state: Literal["UNKNOWN_EFFECT"]
    harness_effect_resolution_performed: Literal[False] = False

    @model_validator(mode="after")
    def _require_observation_not_before_first_sighting(self) -> Self:
        first = TimestampOrder.model_validate(self.first_observed_order)
        observed = TimestampOrder.model_validate(self.observed_order)
        if observed.timestamp < first.timestamp:
            raise ValueError("observed_order must not precede first_observed_order")
        if observed.timestamp == first.timestamp:
            if observed.run_id != first.run_id:
                raise ValueError(
                    "equal timestamps require one stable run ordering identity"
                )
            if observed.sequence < first.sequence:
                raise ValueError(
                    "observed_order sequence must not precede first observation"
                )
        return self


class UnknownEffectDurabilityAssessment(_FrozenStrictModel):
    """Evidence that one unresolved effect remained present and bound."""

    effect_identity: _OpaqueId
    previous_observation_id: _OpaqueId
    current_observation_id: _OpaqueId
    unknown_effect_preserved: Literal[True] = True
    provenance_preserved: Literal[True] = True


class StateObservationAdapter:
    """Revalidate observation payloads without state or effect operations."""

    __slots__ = ()

    def observe_transition(
        self,
        payload: Mapping[str, object] | StateTransitionObservation,
    ) -> StateTransitionObservation:
        if isinstance(payload, StateTransitionObservation):
            return StateTransitionObservation.model_validate(payload)
        if isinstance(payload, Mapping):
            return StateTransitionObservation.model_validate(dict(payload))
        raise TypeError("transition payload must be a mapping or observation")

    def observe_unknown_effect(
        self,
        payload: Mapping[str, object] | UnknownEffectObservation,
    ) -> UnknownEffectObservation:
        if isinstance(payload, UnknownEffectObservation):
            return UnknownEffectObservation.model_validate(payload)
        if isinstance(payload, Mapping):
            return UnknownEffectObservation.model_validate(dict(payload))
        raise TypeError("unknown-effect payload must be a mapping or observation")


class SingleWriterProvenanceChecker:
    """Check a supplied trace without assigning canonical state ownership."""

    __slots__ = ()

    def check(
        self,
        state_subject_identity: str,
        observations: Iterable[StateTransitionObservation],
    ) -> SingleWriterProvenanceAssessment:
        if isinstance(observations, (str, bytes)):
            raise ValueError("observations must be an iterable")
        validated = tuple(
            StateTransitionObservation.model_validate(item) for item in observations
        )
        if not validated:
            raise ValueError("writer provenance requires at least one observation")

        observation_ids = tuple(item.observation_id for item in validated)
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("transition observation identities must be unique")
        if any(
            item.before.state_subject_identity != state_subject_identity
            for item in validated
        ):
            raise StateSubjectMismatchError(
                "all observations must bind requested state subject identity: "
                f"{state_subject_identity}"
            )

        writers = {item.observed_writer_identity for item in validated}
        if len(writers) != 1:
            raise ConflictingWriterProvenanceError(
                "conflicting observed state-writer identities: "
                f"{sorted(writers)}"
            )
        return SingleWriterProvenanceAssessment(
            state_subject_identity=state_subject_identity,
            observation_ids=observation_ids,
            observed_writer_identity=next(iter(writers)),
            provenance_consistent=True,
        )


def _is_strictly_later(
    current: TimestampOrder,
    previous: TimestampOrder,
) -> bool:
    if current.timestamp > previous.timestamp:
        return True
    if current.timestamp < previous.timestamp:
        return False
    return current.run_id == previous.run_id and current.sequence > previous.sequence


class UnknownEffectDurabilityChecker:
    """Fail closed if unresolved-effect evidence disappears or drifts."""

    __slots__ = ()

    def assert_retained(
        self,
        previous: UnknownEffectObservation,
        current: UnknownEffectObservation | None,
    ) -> UnknownEffectDurabilityAssessment:
        validated_previous = UnknownEffectObservation.model_validate(previous)
        if current is None:
            raise MissingUnknownEffectObservationError(
                "UNKNOWN_EFFECT observation disappeared before resolution evidence"
            )
        validated_current = UnknownEffectObservation.model_validate(current)

        previous_binding = (
            validated_previous.effect_identity,
            validated_previous.state_subject_identity,
            validated_previous.origin_transition_observation_id,
            validated_previous.provenance_reference,
            validated_previous.first_observed_order,
        )
        current_binding = (
            validated_current.effect_identity,
            validated_current.state_subject_identity,
            validated_current.origin_transition_observation_id,
            validated_current.provenance_reference,
            validated_current.first_observed_order,
        )
        if current_binding != previous_binding:
            raise UnknownEffectProvenanceDriftError(
                "UNKNOWN_EFFECT identity, origin, or provenance changed"
            )
        if not _is_strictly_later(
            validated_current.observed_order,
            validated_previous.observed_order,
        ):
            raise UnknownEffectOrderError(
                "current UNKNOWN_EFFECT observation must be later than previous"
            )
        return UnknownEffectDurabilityAssessment(
            effect_identity=validated_current.effect_identity,
            previous_observation_id=validated_previous.observation_id,
            current_observation_id=validated_current.observation_id,
            unknown_effect_preserved=True,
            provenance_preserved=True,
        )
