"""WP-EH-AUTHOBS: authority-decision evidence without authority effects."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance.authority_observation import (
    AuthorityDecisionCaptureAdapter,
    AuthorityDecisionKind,
    AuthorityDecisionLineageChecker,
    AuthorityDecisionObservation,
    AuthorityDecisionOrderError,
    AuthorityLineageMismatchError,
    GrantConsumptionEvidenceChecker,
    GrantConsumptionObservation,
    MissingGrantLineageError,
)
from atlas.acceptance.core import TimestampOrder


def _order(sequence: int) -> TimestampOrder:
    return TimestampOrder(
        timestamp=datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc),
        run_id="run-authobs-001",
        sequence=sequence,
    )


def _decision(
    kind: AuthorityDecisionKind,
    decision_id: str,
    sequence: int,
    **updates: object,
) -> AuthorityDecisionObservation:
    parent = (
        "grant-decision-001"
        if kind in {AuthorityDecisionKind.REVOKE, AuthorityDecisionKind.EXPIRY}
        else None
    )
    payload: dict[str, object] = {
        "decision_id": decision_id,
        "lineage_id": "authority-lineage-001",
        "kind": kind,
        "principal_identity": "principal-001",
        "effect_identity": "effect-send-message-001",
        "scope_sha256": "a" * 64,
        "effect_authorizer_identity": "ARC-C04",
        "decision_evidence_reference": f"evidence:{decision_id}",
        "timestamp_order": _order(sequence),
        "grant_decision_id": parent,
        "harness_authority_change_performed": False,
    }
    payload.update(updates)
    return AuthorityDecisionObservation.model_validate(payload)


def _grant() -> AuthorityDecisionObservation:
    return _decision(
        AuthorityDecisionKind.GRANT,
        "grant-decision-001",
        1,
    )


def _consumption(**updates: object) -> GrantConsumptionObservation:
    payload: dict[str, object] = {
        "consumption_observation_id": "grant-consumption-001",
        "grant_decision_id": "grant-decision-001",
        "lineage_id": "authority-lineage-001",
        "principal_identity": "principal-001",
        "effect_identity": "effect-send-message-001",
        "scope_sha256": "a" * 64,
        "grant_consumer_identity": "ARC-C12",
        "consumption_evidence_reference": "evidence:grant-consumption-001",
        "timestamp_order": _order(2),
        "harness_effect_execution_performed": False,
    }
    payload.update(updates)
    return GrantConsumptionObservation.model_validate(payload)


@pytest.mark.parametrize("kind", tuple(AuthorityDecisionKind))
def test_capture_preserves_each_authority_decision_kind_without_effect(
    kind: AuthorityDecisionKind,
) -> None:
    decision = _decision(kind, f"decision-{kind.value.lower()}-001", 1)

    captured = AuthorityDecisionCaptureAdapter().capture(decision)

    assert captured.kind is kind
    assert captured.effect_authorizer_identity == "ARC-C04"
    assert captured.harness_authority_change_performed is False
    assert "result" not in type(captured).model_fields
    with pytest.raises(ValidationError):
        captured.principal_identity = "different"  # type: ignore[misc]


def test_terminal_decision_requires_grant_lineage_but_root_decisions_forbid_it() -> None:
    with pytest.raises(ValidationError, match="must name grant_decision_id"):
        _decision(
            AuthorityDecisionKind.REVOKE,
            "revoke-decision-001",
            2,
            grant_decision_id=None,
        )

    with pytest.raises(ValidationError, match="must not name grant_decision_id"):
        _decision(
            AuthorityDecisionKind.DENY,
            "deny-decision-001",
            1,
            grant_decision_id="grant-decision-001",
        )


def test_capture_revalidates_authorizer_and_authority_change_bypasses() -> None:
    with pytest.raises(ValidationError):
        _decision(
            AuthorityDecisionKind.GRANT,
            "grant-decision-001",
            1,
            effect_authorizer_identity="ARC-C12",
        )

    forged = AuthorityDecisionObservation.model_construct(
        **{
            **_grant().model_dump(),
            "harness_authority_change_performed": True,
        }
    )
    with pytest.raises(ValidationError):
        AuthorityDecisionCaptureAdapter().capture(forged)


def test_lineage_preserves_grant_revoke_and_expiry_evidence_in_order() -> None:
    grant = _grant()
    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        2,
    )
    expiry = _decision(
        AuthorityDecisionKind.EXPIRY,
        "expiry-decision-001",
        3,
    )

    lineage = AuthorityDecisionLineageChecker().trace((grant, revoke, expiry))

    assert lineage.lineage_id == "authority-lineage-001"
    assert lineage.decision_ids == (
        "grant-decision-001",
        "revoke-decision-001",
        "expiry-decision-001",
    )
    assert lineage.kinds == (
        AuthorityDecisionKind.GRANT,
        AuthorityDecisionKind.REVOKE,
        AuthorityDecisionKind.EXPIRY,
    )
    assert lineage.observed_authorizer_identity == "ARC-C04"
    assert lineage.lineage_bound is True
    assert "current_authority" not in type(lineage).model_fields


def test_denial_is_retained_as_decision_evidence_not_a_grant() -> None:
    denial = _decision(
        AuthorityDecisionKind.DENY,
        "deny-decision-001",
        1,
    )

    lineage = AuthorityDecisionLineageChecker().trace((denial,))

    assert lineage.kinds == (AuthorityDecisionKind.DENY,)
    assert "authority_granted" not in type(lineage).model_fields


def test_terminal_decision_rejects_missing_or_later_grant_reference() -> None:
    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        1,
    )
    grant = _grant().model_copy(update={"timestamp_order": _order(2)})

    with pytest.raises(MissingGrantLineageError, match="preceding GRANT"):
        AuthorityDecisionLineageChecker().trace((revoke, grant))


@pytest.mark.parametrize(
    "updates",
    (
        {"lineage_id": "authority-lineage-002"},
        {"principal_identity": "principal-002"},
        {"effect_identity": "effect-send-message-002"},
        {"scope_sha256": "b" * 64},
    ),
)
def test_lineage_rejects_identity_or_scope_substitution(
    updates: dict[str, object],
) -> None:
    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        2,
    ).model_copy(update=updates)

    with pytest.raises(AuthorityLineageMismatchError):
        AuthorityDecisionLineageChecker().trace((_grant(), revoke))


def test_lineage_rejects_duplicate_decision_or_order_identity() -> None:
    grant = _grant()
    with pytest.raises(ValueError, match="decision identities"):
        AuthorityDecisionLineageChecker().trace((grant, grant))

    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        1,
    )
    with pytest.raises(AuthorityDecisionOrderError, match="ordering identities"):
        AuthorityDecisionLineageChecker().trace((grant, revoke))


def test_grant_consumption_evidence_binds_arc_c12_without_executing() -> None:
    binding = GrantConsumptionEvidenceChecker().bind(_grant(), _consumption())

    assert binding.grant.kind is AuthorityDecisionKind.GRANT
    assert binding.consumption.grant_consumer_identity == "ARC-C12"
    assert binding.consumption.harness_effect_execution_performed is False
    assert binding.lineage_bound is True


@pytest.mark.parametrize(
    "updates",
    (
        {"grant_decision_id": "grant-decision-002"},
        {"lineage_id": "authority-lineage-002"},
        {"principal_identity": "principal-002"},
        {"effect_identity": "effect-send-message-002"},
        {"scope_sha256": "b" * 64},
    ),
)
def test_grant_consumption_rejects_lineage_or_scope_substitution(
    updates: dict[str, object],
) -> None:
    consumption = _consumption().model_copy(update=updates)

    with pytest.raises(AuthorityLineageMismatchError):
        GrantConsumptionEvidenceChecker().bind(_grant(), consumption)


def test_grant_consumption_rejects_wrong_role_non_grant_and_order() -> None:
    with pytest.raises(ValidationError):
        _consumption(grant_consumer_identity="ARC-C04")

    denial = _decision(
        AuthorityDecisionKind.DENY,
        "deny-decision-001",
        1,
    )
    with pytest.raises(MissingGrantLineageError, match="GRANT"):
        GrantConsumptionEvidenceChecker().bind(denial, _consumption())

    early_consumption = _consumption(timestamp_order=_order(0))
    with pytest.raises(AuthorityDecisionOrderError, match="later"):
        GrantConsumptionEvidenceChecker().bind(_grant(), early_consumption)


def test_authority_observation_seam_has_no_authorize_grant_revoke_or_execute_api() -> None:
    candidates = (
        AuthorityDecisionCaptureAdapter(),
        AuthorityDecisionLineageChecker(),
        GrantConsumptionEvidenceChecker(),
    )
    for candidate in candidates:
        assert not hasattr(candidate, "authorize")
        assert not hasattr(candidate, "grant")
        assert not hasattr(candidate, "deny")
        assert not hasattr(candidate, "revoke")
        assert not hasattr(candidate, "execute")
        assert not hasattr(candidate, "persist")
