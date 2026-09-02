"""WP-EH-AUTHOBS: authority decision and grant-lineage observations.

The seam captures immutable GRANT, DENY, REVOKE and EXPIRY evidence and checks
their supplied lineage. ARC-C04 remains the sole observed effect authorizer;
ARC-C12 appears only in evidence that a grant was consumed. No operation here
grants, widens, revokes, expires, persists, or executes authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from atlas.acceptance.core import (
    TimestampOrder,
    _FrozenStrictModel,
    _NonEmptyText,
    _OpaqueId,
    _Sha256,
)


class AuthorityLineageMismatchError(ValueError):
    """Raised when decision or consumption evidence changes a lineage binding."""


class MissingGrantLineageError(ValueError):
    """Raised when terminal or consumption evidence lacks a prior GRANT."""


class AuthorityDecisionOrderError(ValueError):
    """Raised when evidence ordering is duplicate or causally reversed."""


class AuthorityDecisionKind(str, Enum):
    """Decision kinds observed by the bounded authority-evidence seam."""

    GRANT = "GRANT"
    DENY = "DENY"
    REVOKE = "REVOKE"
    EXPIRY = "EXPIRY"


_TERMINAL_GRANT_KINDS = frozenset(
    {AuthorityDecisionKind.REVOKE, AuthorityDecisionKind.EXPIRY}
)


class AuthorityDecisionObservation(_FrozenStrictModel):
    """One evidence-bound decision emitted elsewhere by ARC-C04."""

    decision_id: _OpaqueId
    lineage_id: _OpaqueId
    kind: AuthorityDecisionKind
    principal_identity: _OpaqueId
    effect_identity: _OpaqueId
    scope_sha256: _Sha256
    effect_authorizer_identity: Literal["ARC-C04"]
    decision_evidence_reference: _NonEmptyText
    timestamp_order: TimestampOrder
    grant_decision_id: _OpaqueId | None = None
    harness_authority_change_performed: Literal[False] = False

    @field_validator("kind", mode="before")
    @classmethod
    def _require_exact_decision_kind(cls, value: object) -> object:
        if isinstance(value, AuthorityDecisionKind):
            return value
        if not isinstance(value, str):
            raise ValueError("authority decision kind must be an exact string")
        return value

    @model_validator(mode="after")
    def _require_grant_reference_only_for_terminal_decisions(self) -> Self:
        if self.kind in _TERMINAL_GRANT_KINDS:
            if self.grant_decision_id is None:
                raise ValueError(
                    "REVOKE or EXPIRY must name grant_decision_id"
                )
        elif self.grant_decision_id is not None:
            raise ValueError("GRANT or DENY must not name grant_decision_id")
        return self


class AuthorityDecisionLineageEvidence(_FrozenStrictModel):
    """A complete supplied decision trace, not a current-authority verdict."""

    lineage_id: _OpaqueId
    decision_ids: tuple[_OpaqueId, ...]
    kinds: tuple[AuthorityDecisionKind, ...]
    observed_authorizer_identity: Literal["ARC-C04"]
    lineage_bound: Literal[True] = True


class GrantConsumptionObservation(_FrozenStrictModel):
    """Evidence that ARC-C12 consumed a named grant; no execution occurs here."""

    consumption_observation_id: _OpaqueId
    grant_decision_id: _OpaqueId
    lineage_id: _OpaqueId
    principal_identity: _OpaqueId
    effect_identity: _OpaqueId
    scope_sha256: _Sha256
    grant_consumer_identity: Literal["ARC-C12"]
    consumption_evidence_reference: _NonEmptyText
    timestamp_order: TimestampOrder
    harness_effect_execution_performed: Literal[False] = False


class GrantConsumptionEvidenceBinding(_FrozenStrictModel):
    """A structural grant-to-consumption evidence binding."""

    grant: AuthorityDecisionObservation
    consumption: GrantConsumptionObservation
    lineage_bound: Literal[True] = True


class AuthorityDecisionCaptureAdapter:
    """Revalidate decision evidence without invoking an authority operation."""

    __slots__ = ()

    def capture(
        self,
        payload: Mapping[str, object] | AuthorityDecisionObservation,
    ) -> AuthorityDecisionObservation:
        if isinstance(payload, AuthorityDecisionObservation):
            return AuthorityDecisionObservation.model_validate(payload)
        if isinstance(payload, Mapping):
            return AuthorityDecisionObservation.model_validate(dict(payload))
        raise TypeError("decision payload must be a mapping or observation")


def _same_lineage_binding(
    left: AuthorityDecisionObservation,
    right: AuthorityDecisionObservation,
) -> bool:
    return (
        left.lineage_id,
        left.principal_identity,
        left.effect_identity,
        left.scope_sha256,
        left.effect_authorizer_identity,
    ) == (
        right.lineage_id,
        right.principal_identity,
        right.effect_identity,
        right.scope_sha256,
        right.effect_authorizer_identity,
    )


class AuthorityDecisionLineageChecker:
    """Validate identity and causal references in supplied decision evidence."""

    __slots__ = ()

    def trace(
        self,
        observations: Iterable[AuthorityDecisionObservation],
    ) -> AuthorityDecisionLineageEvidence:
        if isinstance(observations, (str, bytes)):
            raise ValueError("observations must be an iterable")
        validated = tuple(
            AuthorityDecisionObservation.model_validate(item)
            for item in observations
        )
        if not validated:
            raise ValueError("authority lineage requires at least one decision")

        decision_ids = tuple(item.decision_id for item in validated)
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("authority decision identities must be unique")
        ordering_ids = tuple(
            (item.timestamp_order.run_id, item.timestamp_order.sequence)
            for item in validated
        )
        if len(set(ordering_ids)) != len(ordering_ids):
            raise AuthorityDecisionOrderError(
                "authority decision ordering identities must be unique"
            )

        root = validated[0]
        seen_grants: set[str] = set()
        for item in validated:
            if not _same_lineage_binding(root, item):
                raise AuthorityLineageMismatchError(
                    "decision changed lineage, principal, effect, scope, or authorizer"
                )
            if item.kind in _TERMINAL_GRANT_KINDS:
                if item.grant_decision_id not in seen_grants:
                    raise MissingGrantLineageError(
                        "REVOKE or EXPIRY must reference a preceding GRANT decision"
                    )
            elif item.kind is AuthorityDecisionKind.GRANT:
                seen_grants.add(item.decision_id)

        return AuthorityDecisionLineageEvidence(
            lineage_id=root.lineage_id,
            decision_ids=decision_ids,
            kinds=tuple(item.kind for item in validated),
            observed_authorizer_identity="ARC-C04",
            lineage_bound=True,
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


class GrantConsumptionEvidenceChecker:
    """Bind read-only ARC-C12 consumption evidence to one ARC-C04 grant."""

    __slots__ = ()

    def bind(
        self,
        grant: AuthorityDecisionObservation,
        consumption: GrantConsumptionObservation,
    ) -> GrantConsumptionEvidenceBinding:
        validated_grant = AuthorityDecisionObservation.model_validate(grant)
        validated_consumption = GrantConsumptionObservation.model_validate(consumption)
        if validated_grant.kind is not AuthorityDecisionKind.GRANT:
            raise MissingGrantLineageError(
                "grant consumption evidence must reference a GRANT decision"
            )
        grant_binding = (
            validated_grant.decision_id,
            validated_grant.lineage_id,
            validated_grant.principal_identity,
            validated_grant.effect_identity,
            validated_grant.scope_sha256,
        )
        consumption_binding = (
            validated_consumption.grant_decision_id,
            validated_consumption.lineage_id,
            validated_consumption.principal_identity,
            validated_consumption.effect_identity,
            validated_consumption.scope_sha256,
        )
        if consumption_binding != grant_binding:
            raise AuthorityLineageMismatchError(
                "consumption changed grant identity, lineage, principal, effect, or scope"
            )
        if not _is_strictly_later(
            validated_consumption.timestamp_order,
            validated_grant.timestamp_order,
        ):
            raise AuthorityDecisionOrderError(
                "grant consumption evidence must be later than its GRANT"
            )
        return GrantConsumptionEvidenceBinding(
            grant=validated_grant,
            consumption=validated_consumption,
            lineage_bound=True,
        )
