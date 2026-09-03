"""WP-EH-AUTHOBS: authority decision and grant-lineage observations.

The seam captures immutable GRANT, DENY, REVOKE and EXPIRY evidence and checks
their supplied lineage. ARC-C04 remains the sole observed effect authorizer;
ARC-C12 appears only in evidence that a grant was consumed. No operation here
grants, widens, revokes, expires, persists, or executes authority.
"""

from __future__ import annotations

import hashlib
import json
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


class AuthorityLineageContextState(str, Enum):
    """Completeness of the supplied read-only authority lineage evidence."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class ObservedGrantState(str, Enum):
    """State evidenced for the specifically referenced decision at consumption."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


class ConsumptionTemporalValidity(str, Enum):
    """Temporal relation only; not an authority or acceptance verdict."""

    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


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


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _observations_sha256(
    observations: tuple[AuthorityDecisionObservation, ...],
) -> str:
    return _canonical_sha256(
        {
            "binding_schema": "WP-EH-AUTHOBS-OBSERVATIONS-v1",
            "observations": tuple(
                item.model_dump(mode="json") for item in observations
            ),
        }
    )


def _context_evidence_sha256(
    *,
    evidence_reference: str,
    lineage_id: str,
    context_state: AuthorityLineageContextState,
    covered_decision_ids: tuple[str, ...],
    covered_observations_sha256: str,
    context_unresolved_reason: str | None,
) -> str:
    return _canonical_sha256(
        {
            "binding_schema": "WP-EH-AUTHOBS-CONTEXT-EVIDENCE-v1",
            "evidence_reference": evidence_reference,
            "lineage_id": lineage_id,
            "context_state": context_state.value,
            "covered_decision_ids": covered_decision_ids,
            "covered_observations_sha256": covered_observations_sha256,
            "context_unresolved_reason": context_unresolved_reason,
        }
    )


class AuthorityLineageContextEvidence(_FrozenStrictModel):
    """Content-addressed context claim; never proof of external completeness truth."""

    evidence_reference: _NonEmptyText
    lineage_id: _OpaqueId
    context_state: AuthorityLineageContextState
    covered_decision_ids: tuple[_OpaqueId, ...]
    covered_observations_sha256: _Sha256
    context_unresolved_reason: _NonEmptyText | None
    context_evidence_sha256: _Sha256

    @classmethod
    def from_observations(
        cls,
        observations: Iterable[AuthorityDecisionObservation],
        *,
        context_state: AuthorityLineageContextState,
        evidence_reference: str,
        context_unresolved_reason: str | None,
    ) -> AuthorityLineageContextEvidence:
        """Record caller-supplied provenance without authenticating its truth."""

        if isinstance(observations, (str, bytes)):
            raise ValueError("context observations must be an iterable")
        if not isinstance(context_state, AuthorityLineageContextState):
            raise TypeError("context_state must be AuthorityLineageContextState")
        validated = tuple(
            AuthorityDecisionObservation.model_validate(item)
            for item in observations
        )
        if not validated:
            raise ValueError("context evidence requires at least one observation")
        lineage_id = validated[0].lineage_id
        decision_ids = tuple(item.decision_id for item in validated)
        observations_sha256 = _observations_sha256(validated)
        evidence_sha256 = _context_evidence_sha256(
            evidence_reference=evidence_reference,
            lineage_id=lineage_id,
            context_state=context_state,
            covered_decision_ids=decision_ids,
            covered_observations_sha256=observations_sha256,
            context_unresolved_reason=context_unresolved_reason,
        )
        return cls(
            evidence_reference=evidence_reference,
            lineage_id=lineage_id,
            context_state=context_state,
            covered_decision_ids=decision_ids,
            covered_observations_sha256=observations_sha256,
            context_unresolved_reason=context_unresolved_reason,
            context_evidence_sha256=evidence_sha256,
        )

    @field_validator("covered_decision_ids")
    @classmethod
    def _require_unique_covered_decisions(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not value:
            raise ValueError("context evidence must cover at least one decision")
        if len(set(value)) != len(value):
            raise ValueError("covered decision identities must be unique")
        return value

    @model_validator(mode="after")
    def _require_bound_context_claim(self) -> Self:
        if self.context_state is AuthorityLineageContextState.COMPLETE:
            if self.context_unresolved_reason is not None:
                raise ValueError(
                    "COMPLETE context must not carry an unresolved reason"
                )
        elif self.context_unresolved_reason is None:
            raise ValueError(
                "INCOMPLETE or UNKNOWN context requires an unresolved reason"
            )

        expected_sha256 = _context_evidence_sha256(
            evidence_reference=self.evidence_reference,
            lineage_id=self.lineage_id,
            context_state=self.context_state,
            covered_decision_ids=self.covered_decision_ids,
            covered_observations_sha256=self.covered_observations_sha256,
            context_unresolved_reason=self.context_unresolved_reason,
        )
        if self.context_evidence_sha256 != expected_sha256:
            raise ValueError("context evidence content binding is inconsistent")
        return self


def _context_binding_sha256(
    observations: tuple[AuthorityDecisionObservation, ...],
    context_evidence: AuthorityLineageContextEvidence,
) -> str:
    """Bind an evidence identity to observations without authenticating it."""

    return _canonical_sha256(
        {
            "binding_schema": "WP-EH-AUTHOBS-CONTEXT-v2",
            "observations": tuple(
                item.model_dump(mode="json") for item in observations
            ),
            "context_evidence": context_evidence.model_dump(mode="json"),
        }
    )


class AuthorityDecisionLineageEvidence(_FrozenStrictModel):
    """A supplied decision trace with context provenance, not an authority verdict."""

    lineage_id: _OpaqueId
    observations: tuple[AuthorityDecisionObservation, ...]
    decision_ids: tuple[_OpaqueId, ...]
    kinds: tuple[AuthorityDecisionKind, ...]
    observed_authorizer_identity: Literal["ARC-C04"]
    context_state: AuthorityLineageContextState
    context_evidence: AuthorityLineageContextEvidence
    context_binding_sha256: _Sha256
    lineage_bound: Literal[True] = True

    @model_validator(mode="after")
    def _require_bound_context_evidence(self) -> Self:
        decision_ids = tuple(item.decision_id for item in self.observations)
        kinds = tuple(item.kind for item in self.observations)
        if self.decision_ids != decision_ids or self.kinds != kinds:
            raise ValueError("lineage summary does not match its observations")
        if self.context_state is not self.context_evidence.context_state:
            raise ValueError("context state summary contradicts context evidence")
        if self.lineage_id != self.context_evidence.lineage_id:
            raise ValueError("lineage identity contradicts context evidence")
        if self.context_evidence.covered_decision_ids != decision_ids:
            raise ValueError("context evidence does not cover the supplied decisions")
        if self.context_evidence.covered_observations_sha256 != (
            _observations_sha256(self.observations)
        ):
            raise ValueError("context evidence does not cover supplied observations")

        expected_binding = _context_binding_sha256(
            self.observations,
            self.context_evidence,
        )
        if self.context_binding_sha256 != expected_binding:
            raise ValueError(
                "context binding does not match observations and context evidence"
            )
        return self


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
    """Causal consumption assessment; affirmative only for known active grants."""

    lineage: AuthorityDecisionLineageEvidence
    referenced_decision: AuthorityDecisionObservation | None
    consumption: GrantConsumptionObservation
    grant_state: ObservedGrantState
    temporal_validity: ConsumptionTemporalValidity
    lineage_bound: bool

    @model_validator(mode="after")
    def _require_affirmative_state_consistency(self) -> Self:
        should_be_affirmative = (
            self.lineage.context_state is AuthorityLineageContextState.COMPLETE
            and self.grant_state is ObservedGrantState.ACTIVE
            and self.temporal_validity is ConsumptionTemporalValidity.VALID
        )
        if self.lineage_bound != should_be_affirmative:
            raise ValueError("lineage_bound contradicts causal grant state")
        if self.grant_state is ObservedGrantState.ACTIVE and (
            self.referenced_decision is None
            or self.referenced_decision.kind is not AuthorityDecisionKind.GRANT
        ):
            raise ValueError("ACTIVE state requires the referenced GRANT decision")
        if self.grant_state is ObservedGrantState.DENIED and (
            self.referenced_decision is None
            or self.referenced_decision.kind is not AuthorityDecisionKind.DENY
        ):
            raise ValueError("DENIED state requires the referenced DENY decision")
        return self


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
        *,
        context_evidence: AuthorityLineageContextEvidence,
    ) -> AuthorityDecisionLineageEvidence:
        if isinstance(observations, (str, bytes)):
            raise ValueError("observations must be an iterable")
        validated = tuple(
            AuthorityDecisionObservation.model_validate(item)
            for item in observations
        )
        if not validated:
            raise ValueError("authority lineage requires at least one decision")
        validated_context = AuthorityLineageContextEvidence.model_validate(
            context_evidence
        )

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
        seen_grants: dict[str, AuthorityDecisionObservation] = {}
        previous: AuthorityDecisionObservation | None = None
        for item in validated:
            if not _same_lineage_binding(root, item):
                raise AuthorityLineageMismatchError(
                    "decision changed lineage, principal, effect, scope, or authorizer"
                )
            if previous is not None and not _is_strictly_later(
                item.timestamp_order,
                previous.timestamp_order,
            ):
                raise AuthorityDecisionOrderError(
                    "each tuple decision must be causally later in TimestampOrder"
                )
            if item.kind in _TERMINAL_GRANT_KINDS:
                referenced_grant = seen_grants.get(item.grant_decision_id or "")
                if referenced_grant is None:
                    raise MissingGrantLineageError(
                        "REVOKE or EXPIRY must reference a preceding GRANT decision"
                    )
                if not _is_strictly_later(
                    item.timestamp_order,
                    referenced_grant.timestamp_order,
                ):
                    raise AuthorityDecisionOrderError(
                        "REVOKE or EXPIRY must be causally later than its GRANT"
                    )
            elif item.kind is AuthorityDecisionKind.GRANT:
                seen_grants[item.decision_id] = item
            previous = item

        kinds = tuple(item.kind for item in validated)
        if validated_context.lineage_id != root.lineage_id:
            raise AuthorityLineageMismatchError(
                "context evidence changed authority lineage identity"
            )
        if validated_context.covered_decision_ids != decision_ids:
            raise AuthorityLineageMismatchError(
                "context evidence does not cover the traced decision identities"
            )
        if validated_context.covered_observations_sha256 != _observations_sha256(
            validated
        ):
            raise AuthorityLineageMismatchError(
                "context evidence does not cover the traced observations"
            )
        context_binding_sha256 = _context_binding_sha256(
            validated,
            validated_context,
        )
        return AuthorityDecisionLineageEvidence(
            lineage_id=root.lineage_id,
            observations=validated,
            decision_ids=decision_ids,
            kinds=kinds,
            observed_authorizer_identity="ARC-C04",
            context_state=validated_context.context_state,
            context_evidence=validated_context,
            context_binding_sha256=context_binding_sha256,
            lineage_bound=True,
        )


def _is_strictly_later(
    current: TimestampOrder,
    previous: TimestampOrder,
) -> bool:
    if current.timestamp < previous.timestamp:
        return False
    if current.run_id == previous.run_id:
        return current.sequence > previous.sequence
    return current.timestamp > previous.timestamp


def _consumption_matches_decision(
    decision: AuthorityDecisionObservation,
    consumption: GrantConsumptionObservation,
) -> bool:
    return (
        decision.decision_id,
        decision.lineage_id,
        decision.principal_identity,
        decision.effect_identity,
        decision.scope_sha256,
    ) == (
        consumption.grant_decision_id,
        consumption.lineage_id,
        consumption.principal_identity,
        consumption.effect_identity,
        consumption.scope_sha256,
    )


class GrantConsumptionEvidenceChecker:
    """Bind read-only ARC-C12 consumption evidence to one ARC-C04 grant."""

    __slots__ = ()

    def bind(
        self,
        lineage: AuthorityDecisionLineageEvidence,
        consumption: GrantConsumptionObservation,
    ) -> GrantConsumptionEvidenceBinding:
        if not isinstance(lineage, AuthorityDecisionLineageEvidence):
            raise TypeError("lineage evidence from trace() is required")
        validated_lineage = AuthorityDecisionLineageEvidence.model_validate(lineage)
        reconstructed_lineage = AuthorityDecisionLineageChecker().trace(
            validated_lineage.observations,
            context_evidence=validated_lineage.context_evidence,
        )
        if reconstructed_lineage != validated_lineage:
            raise AuthorityLineageMismatchError(
                "lineage summary does not match its decision observations"
            )
        validated_consumption = GrantConsumptionObservation.model_validate(consumption)
        referenced_decision = next(
            (
                item
                for item in validated_lineage.observations
                if item.decision_id == validated_consumption.grant_decision_id
            ),
            None,
        )
        if referenced_decision is None:
            if validated_lineage.context_state is AuthorityLineageContextState.COMPLETE:
                raise AuthorityLineageMismatchError(
                    "consumption names no decision in the complete lineage"
                )
            return GrantConsumptionEvidenceBinding(
                lineage=validated_lineage,
                referenced_decision=None,
                consumption=validated_consumption,
                grant_state=ObservedGrantState.UNKNOWN,
                temporal_validity=ConsumptionTemporalValidity.UNKNOWN,
                lineage_bound=False,
            )
        if not _consumption_matches_decision(
            referenced_decision,
            validated_consumption,
        ):
            raise AuthorityLineageMismatchError(
                "consumption changed grant identity, lineage, principal, effect, or scope"
            )

        if referenced_decision.kind is AuthorityDecisionKind.DENY:
            return GrantConsumptionEvidenceBinding(
                lineage=validated_lineage,
                referenced_decision=referenced_decision,
                consumption=validated_consumption,
                grant_state=ObservedGrantState.DENIED,
                temporal_validity=ConsumptionTemporalValidity.INVALID,
                lineage_bound=False,
            )
        if referenced_decision.kind is not AuthorityDecisionKind.GRANT:
            raise MissingGrantLineageError(
                "grant consumption evidence must reference a GRANT decision"
            )

        if not _is_strictly_later(
            validated_consumption.timestamp_order,
            referenced_decision.timestamp_order,
        ):
            grant_state = (
                ObservedGrantState.ACTIVE
                if validated_lineage.context_state
                is AuthorityLineageContextState.COMPLETE
                else ObservedGrantState.UNKNOWN
            )
            return GrantConsumptionEvidenceBinding(
                lineage=validated_lineage,
                referenced_decision=referenced_decision,
                consumption=validated_consumption,
                grant_state=grant_state,
                temporal_validity=ConsumptionTemporalValidity.INVALID,
                lineage_bound=False,
            )

        terminal_decisions = tuple(
            item
            for item in validated_lineage.observations
            if item.kind in _TERMINAL_GRANT_KINDS
            and item.grant_decision_id == referenced_decision.decision_id
        )
        for terminal in terminal_decisions:
            if not _is_strictly_later(
                terminal.timestamp_order,
                validated_consumption.timestamp_order,
            ):
                terminal_state = (
                    ObservedGrantState.REVOKED
                    if terminal.kind is AuthorityDecisionKind.REVOKE
                    else ObservedGrantState.EXPIRED
                )
                return GrantConsumptionEvidenceBinding(
                    lineage=validated_lineage,
                    referenced_decision=referenced_decision,
                    consumption=validated_consumption,
                    grant_state=terminal_state,
                    temporal_validity=ConsumptionTemporalValidity.INVALID,
                    lineage_bound=False,
                )

        if validated_lineage.context_state is not AuthorityLineageContextState.COMPLETE:
            return GrantConsumptionEvidenceBinding(
                lineage=validated_lineage,
                referenced_decision=referenced_decision,
                consumption=validated_consumption,
                grant_state=ObservedGrantState.UNKNOWN,
                temporal_validity=ConsumptionTemporalValidity.UNKNOWN,
                lineage_bound=False,
            )

        return GrantConsumptionEvidenceBinding(
            lineage=validated_lineage,
            referenced_decision=referenced_decision,
            consumption=validated_consumption,
            grant_state=ObservedGrantState.ACTIVE,
            temporal_validity=ConsumptionTemporalValidity.VALID,
            lineage_bound=True,
        )
