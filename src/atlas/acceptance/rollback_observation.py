"""WP-EH-ROLLBACK: rollback eligibility and reversal evidence observations.

The seam records immutable checkpoint identity/provenance, derives eligibility
only from an explicit supplied predicate vector, and verifies that observed
restored content matches a named checkpoint. It does not execute rollback,
write or delete state, change authority, persist evidence, or perform cutover.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from atlas.acceptance.core import (
    TimestampOrder,
    _FrozenStrictModel,
    _NonEmptyText,
    _OpaqueId,
    _Sha256,
)


_StrictBool = Annotated[bool, Field(strict=True)]


class RollbackCheckpointMismatchError(ValueError):
    """Raised when reversal evidence substitutes a checkpoint binding."""


class RollbackCheckpointEvidence(_FrozenStrictModel):
    """Content-bound identity and provenance for one observed checkpoint."""

    checkpoint_id: _OpaqueId
    state_subject_identity: _OpaqueId
    state_version: _OpaqueId
    state_sha256: _Sha256
    provenance_reference: _NonEmptyText
    observed_writer_identity: _OpaqueId
    timestamp_order: TimestampOrder


class RollbackEligibilityPredicateEvidence(_FrozenStrictModel):
    """One caller-supplied named predicate and its evidence reference."""

    predicate_id: _OpaqueId
    satisfied: _StrictBool
    evidence_reference: _NonEmptyText


class RollbackEligibilityAssessment(_FrozenStrictModel):
    """Trace-preserving predicate result, not rollback authority."""

    checkpoint: RollbackCheckpointEvidence
    predicate_trace: tuple[RollbackEligibilityPredicateEvidence, ...]
    eligible: _StrictBool
    harness_rollback_performed: Literal[False] = False

    @model_validator(mode="after")
    def _require_complete_derived_predicate_result(self) -> Self:
        RollbackCheckpointEvidence.model_validate(self.checkpoint)
        trace = tuple(
            RollbackEligibilityPredicateEvidence.model_validate(item)
            for item in self.predicate_trace
        )
        if not trace:
            raise ValueError("rollback eligibility requires at least one predicate")
        predicate_ids = tuple(item.predicate_id for item in trace)
        if len(set(predicate_ids)) != len(predicate_ids):
            raise ValueError("rollback predicate identities must be unique")
        if self.eligible is not all(item.satisfied for item in trace):
            raise ValueError("rollback eligibility must be derived from full trace")
        return self


class RollbackStateEvidence(_FrozenStrictModel):
    """Content-bound state evidence used only for reversal comparison."""

    state_subject_identity: _OpaqueId
    state_version: _OpaqueId
    state_sha256: _Sha256
    evidence_reference: _NonEmptyText


def _is_strictly_later(
    current: TimestampOrder,
    previous: TimestampOrder,
) -> bool:
    if current.timestamp > previous.timestamp:
        return True
    if current.timestamp < previous.timestamp:
        return False
    return current.run_id == previous.run_id and current.sequence > previous.sequence


class RollbackReversalObservation(_FrozenStrictModel):
    """Observed restoration evidence; the harness performs no reversal."""

    observation_id: _OpaqueId
    checkpoint: RollbackCheckpointEvidence
    pre_reversal_state: RollbackStateEvidence
    restored_state: RollbackStateEvidence
    restored_checkpoint_id: _OpaqueId
    reversal_evidence_reference: _NonEmptyText
    timestamp_order: TimestampOrder
    harness_rollback_performed: Literal[False] = False
    harness_state_write_performed: Literal[False] = False
    harness_deletion_performed: Literal[False] = False

    @model_validator(mode="after")
    def _require_checkpoint_bound_reversal_evidence(self) -> Self:
        checkpoint = RollbackCheckpointEvidence.model_validate(self.checkpoint)
        before = RollbackStateEvidence.model_validate(self.pre_reversal_state)
        restored = RollbackStateEvidence.model_validate(self.restored_state)
        subjects = {
            checkpoint.state_subject_identity,
            before.state_subject_identity,
            restored.state_subject_identity,
        }
        if len(subjects) != 1:
            raise ValueError(
                "checkpoint, pre-reversal and restored state subject must match"
            )
        if self.restored_checkpoint_id != checkpoint.checkpoint_id:
            raise ValueError("restored checkpoint identity must match checkpoint")
        if before.state_sha256 == checkpoint.state_sha256:
            raise ValueError(
                "pre-reversal content hash must differ from checkpoint content"
            )
        if restored.state_sha256 != checkpoint.state_sha256:
            raise ValueError(
                "restored content hash must match checkpoint content hash"
            )
        if before.state_version == restored.state_version:
            raise ValueError(
                "restored state version must differ from pre-reversal version"
            )
        if not _is_strictly_later(self.timestamp_order, checkpoint.timestamp_order):
            raise ValueError(
                "reversal observation must be later than checkpoint evidence"
            )
        return self


class ReversalEvidenceAssertion(_FrozenStrictModel):
    """Structural assertion of checkpoint and content binding."""

    checkpoint_id: _OpaqueId
    observation_id: _OpaqueId
    checkpoint_identity_bound: Literal[True] = True
    restored_content_bound: Literal[True] = True


class RollbackEligibilityChecker:
    """Assess only the explicit predicate vector supplied by the caller."""

    __slots__ = ()

    def assess(
        self,
        checkpoint: RollbackCheckpointEvidence,
        predicates: Iterable[RollbackEligibilityPredicateEvidence],
    ) -> RollbackEligibilityAssessment:
        if isinstance(predicates, (str, bytes)):
            raise ValueError("predicates must be an iterable")
        validated_checkpoint = RollbackCheckpointEvidence.model_validate(checkpoint)
        validated_predicates = tuple(
            RollbackEligibilityPredicateEvidence.model_validate(item)
            for item in predicates
        )
        return RollbackEligibilityAssessment(
            checkpoint=validated_checkpoint,
            predicate_trace=validated_predicates,
            eligible=all(item.satisfied for item in validated_predicates),
            harness_rollback_performed=False,
        )


class RollbackObservationAdapter:
    """Revalidate reversal evidence without executing an external effect."""

    __slots__ = ()

    def observe_reversal(
        self,
        payload: Mapping[str, object] | RollbackReversalObservation,
    ) -> RollbackReversalObservation:
        if isinstance(payload, RollbackReversalObservation):
            return RollbackReversalObservation.model_validate(payload)
        if isinstance(payload, Mapping):
            return RollbackReversalObservation.model_validate(dict(payload))
        raise TypeError("reversal payload must be a mapping or observation")


class ReversalEvidenceChecker:
    """Assert exact checkpoint identity and restored content evidence."""

    __slots__ = ()

    def assert_matches_checkpoint(
        self,
        observation: RollbackReversalObservation,
    ) -> ReversalEvidenceAssertion:
        if (
            observation.restored_checkpoint_id
            != observation.checkpoint.checkpoint_id
        ):
            raise RollbackCheckpointMismatchError(
                "restored checkpoint identity does not match observation checkpoint"
            )
        try:
            validated = RollbackReversalObservation.model_validate(observation)
        except ValidationError:
            raise
        if validated.restored_state.state_sha256 != validated.checkpoint.state_sha256:
            raise RollbackCheckpointMismatchError(
                "restored content does not match checkpoint content"
            )
        return ReversalEvidenceAssertion(
            checkpoint_id=validated.checkpoint.checkpoint_id,
            observation_id=validated.observation_id,
            checkpoint_identity_bound=True,
            restored_content_bound=True,
        )
