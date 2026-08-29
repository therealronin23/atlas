"""WP-EH-FAILURE: semantically bounded, non-live failure simulation.

Each scenario is a typed synthetic transition whose validators establish the
named failure boundary.  The harness revalidates and captures those transitions
in raw input order.  It has no callback, executor, result adjudication,
authority, persistence, or live destructive operation surface.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from atlas.acceptance.core import (
    TimestampOrder,
    _ContractId,
    _FrozenStrictModel,
    _NonEmptyText,
    _OpaqueId,
    _Sha256,
)


FAILURE_CORPUS_RETENTION_METADATA = (
    "Retain corpus identity/version and raw evidence as long as dependent "
    "acceptance/rollback/audit claims remain valid; no unratified numeric "
    "duration invented."
)

_PositiveInt = Annotated[int, Field(gt=0, strict=True)]
_AtLeastTwo = Annotated[int, Field(ge=2, strict=True)]


class FailureInjectionMode(str, Enum):
    """Frozen failure boundaries supported as non-live test fixtures."""

    CRASH = "CRASH"
    TIMEOUT = "TIMEOUT"
    RETRY = "RETRY"
    DUPLICATE = "DUPLICATE"
    LOST_ACKNOWLEDGEMENT = "LOST_ACKNOWLEDGEMENT"
    REVOCATION = "REVOCATION"
    EXPIRY = "EXPIRY"
    CONCURRENCY = "CONCURRENCY"
    DELETION = "DELETION"
    ERASURE = "ERASURE"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    CANONICAL_FALSIFIER = "CANONICAL_FALSIFIER"


class CrashFailureScenario(_FrozenStrictModel):
    """A simulated running-to-stopped transition at a named crash point."""

    mode: Literal[FailureInjectionMode.CRASH]
    process_identity: _OpaqueId
    crash_point: _NonEmptyText
    simulated_running_before: Literal[True]
    simulated_running_after: Literal[False]


class TimeoutFailureScenario(_FrozenStrictModel):
    """A simulated observation strictly beyond a positive deadline."""

    mode: Literal[FailureInjectionMode.TIMEOUT]
    operation_identity: _OpaqueId
    deadline_ms: _PositiveInt
    simulated_elapsed_ms: _PositiveInt

    @model_validator(mode="after")
    def _require_elapsed_beyond_deadline(self) -> Self:
        if self.simulated_elapsed_ms <= self.deadline_ms:
            raise ValueError("simulated_elapsed_ms must exceed deadline_ms")
        return self


class RetryFailureScenario(_FrozenStrictModel):
    """A bounded non-initial attempt within an explicit attempt ceiling."""

    mode: Literal[FailureInjectionMode.RETRY]
    operation_identity: _OpaqueId
    attempt_number: _AtLeastTwo
    maximum_attempts: _AtLeastTwo

    @model_validator(mode="after")
    def _require_attempt_within_ceiling(self) -> Self:
        if self.attempt_number > self.maximum_attempts:
            raise ValueError("attempt_number must not exceed maximum_attempts")
        return self


class DuplicateFailureScenario(_FrozenStrictModel):
    """A second-or-later occurrence of one stable delivery identity."""

    mode: Literal[FailureInjectionMode.DUPLICATE]
    delivery_identity: _OpaqueId
    occurrence_number: _AtLeastTwo


class LostAcknowledgementFailureScenario(_FrozenStrictModel):
    """Delivery is simulated as observed while its acknowledgement is absent."""

    mode: Literal[FailureInjectionMode.LOST_ACKNOWLEDGEMENT]
    delivery_identity: _OpaqueId
    simulated_delivery_observed: Literal[True]
    simulated_acknowledgement_observed: Literal[False]


class RevocationFailureScenario(_FrozenStrictModel):
    """A simulated valid-to-invalid transition for a revocable subject."""

    mode: Literal[FailureInjectionMode.REVOCATION]
    subject_identity: _OpaqueId
    simulated_valid_before: Literal[True]
    simulated_valid_after: Literal[False]


class ExpiryFailureScenario(_FrozenStrictModel):
    """A simulated observation strictly after a timezone-bound expiry."""

    mode: Literal[FailureInjectionMode.EXPIRY]
    subject_identity: _OpaqueId
    valid_until: datetime
    simulated_observed_at: datetime

    @field_validator("valid_until", "simulated_observed_at", mode="before")
    @classmethod
    def _require_datetime_or_iso_string(cls, value: object) -> object:
        if not isinstance(value, (datetime, str)):
            raise ValueError("expiry timestamps must be datetimes or ISO strings")
        return value

    @field_validator("valid_until", "simulated_observed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expiry timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def _require_observation_after_expiry(self) -> Self:
        if self.simulated_observed_at <= self.valid_until:
            raise ValueError("simulated_observed_at must be after valid_until")
        return self


class ConcurrencyFailureScenario(_FrozenStrictModel):
    """Two distinct actors compete from the same resource precondition."""

    mode: Literal[FailureInjectionMode.CONCURRENCY]
    resource_identity: _OpaqueId
    shared_precondition_version: _OpaqueId
    competing_actor_identities: tuple[_OpaqueId, _OpaqueId]

    @field_validator("competing_actor_identities")
    @classmethod
    def _require_distinct_competitors(
        cls,
        value: tuple[str, str],
    ) -> tuple[str, str]:
        if value[0] == value[1]:
            raise ValueError("competing_actor_identities must be distinct")
        return value


class DeletionFailureScenario(_FrozenStrictModel):
    """A simulated present-to-absent target transition, never a live deletion."""

    mode: Literal[FailureInjectionMode.DELETION]
    target_identity: _OpaqueId
    simulated_present_before: Literal[True]
    simulated_present_after: Literal[False]


class ErasureFailureScenario(_FrozenStrictModel):
    """A simulated available-to-unavailable key-handle transition."""

    mode: Literal[FailureInjectionMode.ERASURE]
    protected_target_identity: _OpaqueId
    key_handle_identity: _OpaqueId
    simulated_key_available_before: Literal[True]
    simulated_key_available_after: Literal[False]


class PartialFailureScenario(_FrozenStrictModel):
    """A bounded mixed outcome with at least one failed and one intact unit."""

    mode: Literal[FailureInjectionMode.PARTIAL_FAILURE]
    operation_identity: _OpaqueId
    total_units: _AtLeastTwo
    failed_units: _PositiveInt

    @model_validator(mode="after")
    def _require_partial_not_total_failure(self) -> Self:
        if self.failed_units >= self.total_units:
            raise ValueError("failed_units must be less than total_units")
        return self


class CanonicalFalsifierScenario(_FrozenStrictModel):
    """A source-identified counterexample simulated as observed."""

    mode: Literal[FailureInjectionMode.CANONICAL_FALSIFIER]
    source_falsifier_identity: _OpaqueId
    simulated_counterexample_observed: Literal[True]


FailureInjectionScenario = Annotated[
    CrashFailureScenario
    | TimeoutFailureScenario
    | RetryFailureScenario
    | DuplicateFailureScenario
    | LostAcknowledgementFailureScenario
    | RevocationFailureScenario
    | ExpiryFailureScenario
    | ConcurrencyFailureScenario
    | DeletionFailureScenario
    | ErasureFailureScenario
    | PartialFailureScenario
    | CanonicalFalsifierScenario,
    Field(discriminator="mode"),
]


class FailureInjectionFixture(_FrozenStrictModel):
    """One provenance-bound synthetic scenario, not an executable operation."""

    fixture_id: _OpaqueId
    test_contract_id: _ContractId
    semantic_falsifier: _NonEmptyText
    corpus_class_id: Literal["CORPUS-FAILINJ"]
    corpus_version: _NonEmptyText
    source_canon_ids: tuple[_OpaqueId, ...]
    creator_identity: _NonEmptyText
    import_source: _NonEmptyText
    generation_method: _NonEmptyText
    contamination_history: tuple[_NonEmptyText, ...]
    retention_metadata: _NonEmptyText
    raw_order: TimestampOrder
    scenario: FailureInjectionScenario

    @property
    def mode(self) -> FailureInjectionMode:
        """Return the discriminated scenario mode without duplicating state."""

        return self.scenario.mode

    @field_validator("source_canon_ids")
    @classmethod
    def _require_source_provenance(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("source_canon_ids must name at least one source")
        if len(set(value)) != len(value):
            raise ValueError("source_canon_ids must be unique")
        return value

    @field_validator("contamination_history")
    @classmethod
    def _require_unique_contamination_history(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("contamination_history entries must be unique")
        return value

    @field_validator("retention_metadata")
    @classmethod
    def _require_frozen_retention_metadata(cls, value: str) -> str:
        if value != FAILURE_CORPUS_RETENTION_METADATA:
            raise ValueError("retention_metadata must use the frozen instruction")
        return value


def _canonical_fixture_bytes(fixture: FailureInjectionFixture) -> bytes:
    return json.dumps(
        fixture.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _fixture_sha256(fixture: FailureInjectionFixture) -> str:
    return hashlib.sha256(_canonical_fixture_bytes(fixture)).hexdigest()


def _simulate_transition(
    scenario: FailureInjectionScenario,
) -> FailureInjectionScenario:
    """Dispatch and revalidate one mode without invoking any live operation."""

    payload = scenario.model_dump(mode="python")
    if isinstance(scenario, CrashFailureScenario):
        return CrashFailureScenario.model_validate(payload)
    if isinstance(scenario, TimeoutFailureScenario):
        return TimeoutFailureScenario.model_validate(payload)
    if isinstance(scenario, RetryFailureScenario):
        return RetryFailureScenario.model_validate(payload)
    if isinstance(scenario, DuplicateFailureScenario):
        return DuplicateFailureScenario.model_validate(payload)
    if isinstance(scenario, LostAcknowledgementFailureScenario):
        return LostAcknowledgementFailureScenario.model_validate(payload)
    if isinstance(scenario, RevocationFailureScenario):
        return RevocationFailureScenario.model_validate(payload)
    if isinstance(scenario, ExpiryFailureScenario):
        return ExpiryFailureScenario.model_validate(payload)
    if isinstance(scenario, ConcurrencyFailureScenario):
        return ConcurrencyFailureScenario.model_validate(payload)
    if isinstance(scenario, DeletionFailureScenario):
        return DeletionFailureScenario.model_validate(payload)
    if isinstance(scenario, ErasureFailureScenario):
        return ErasureFailureScenario.model_validate(payload)
    if isinstance(scenario, PartialFailureScenario):
        return PartialFailureScenario.model_validate(payload)
    if isinstance(scenario, CanonicalFalsifierScenario):
        return CanonicalFalsifierScenario.model_validate(payload)
    raise TypeError("unsupported failure-injection scenario")


class FailureInjectionObservation(_FrozenStrictModel):
    """One typed, satisfied synthetic transition with no live effect."""

    fixture: FailureInjectionFixture
    fixture_sha256: _Sha256
    simulated_transition: FailureInjectionScenario
    predicate_satisfied: Literal[True] = True
    capture_index: Annotated[int, Field(ge=0, strict=True)]
    live_effect_emitted: Literal[False] = False

    @model_validator(mode="after")
    def _require_fixture_and_transition_binding(self) -> Self:
        fixture = FailureInjectionFixture.model_validate(self.fixture)
        if self.fixture_sha256 != _fixture_sha256(fixture):
            raise ValueError("fixture_sha256 must bind the canonical fixture bytes")
        expected_transition = _simulate_transition(fixture.scenario)
        if (
            type(self.simulated_transition) is not type(expected_transition)
            or self.simulated_transition != expected_transition
        ):
            raise ValueError(
                "simulated_transition must bind the fixture's typed scenario"
            )
        return self


class FailureInjectionTrace(_FrozenStrictModel):
    """Complete declared fixture vector in its original capture order."""

    fixture_ids: tuple[_OpaqueId, ...]
    observations: tuple[FailureInjectionObservation, ...]

    @model_validator(mode="after")
    def _require_complete_unambiguous_order(self) -> Self:
        observations = tuple(
            FailureInjectionObservation.model_validate(item)
            for item in self.observations
        )
        if not observations:
            raise ValueError("failure trace must contain at least one observation")

        observed_ids = tuple(item.fixture.fixture_id for item in observations)
        if len(set(observed_ids)) != len(observed_ids):
            raise ValueError("fixture identities must be unique within a trace")
        if observed_ids != self.fixture_ids:
            raise ValueError(
                "failure observations must cover declared fixture identities in "
                "capture order"
            )

        raw_order_ids = tuple(
            (item.fixture.raw_order.run_id, item.fixture.raw_order.sequence)
            for item in observations
        )
        if len(set(raw_order_ids)) != len(raw_order_ids):
            raise ValueError("raw order identities must be unique within a trace")

        indexes = tuple(item.capture_index for item in observations)
        if indexes != tuple(range(len(observations))):
            raise ValueError("capture indexes must preserve the original input order")
        return self


class FailureInjectionHarness:
    """Dispatch and capture typed failure boundaries without invoking them."""

    __slots__ = ()

    def simulate(
        self,
        fixtures: Iterable[FailureInjectionFixture],
    ) -> FailureInjectionTrace:
        validated = tuple(
            FailureInjectionFixture.model_validate(candidate)
            for candidate in fixtures
        )
        observations = tuple(
            FailureInjectionObservation(
                fixture=fixture,
                fixture_sha256=_fixture_sha256(fixture),
                simulated_transition=_simulate_transition(fixture.scenario),
                predicate_satisfied=True,
                capture_index=index,
                live_effect_emitted=False,
            )
            for index, fixture in enumerate(validated)
        )
        return FailureInjectionTrace(
            fixture_ids=tuple(fixture.fixture_id for fixture in validated),
            observations=observations,
        )
