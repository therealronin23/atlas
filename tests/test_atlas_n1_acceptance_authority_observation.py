"""WP-EH-AUTHOBS: authority-decision evidence without authority effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance.authority_observation import (
    AuthorityLineageContextState,
    AuthorityDecisionCaptureAdapter,
    AuthorityDecisionKind,
    AuthorityDecisionLineageChecker,
    AuthorityDecisionObservation,
    AuthorityDecisionOrderError,
    AuthorityLineageMismatchError,
    ConsumptionTemporalValidity,
    GrantConsumptionEvidenceChecker,
    GrantConsumptionObservation,
    MissingGrantLineageError,
    ObservedGrantState,
)
from atlas.acceptance.core import TimestampOrder


def _order(
    sequence: int,
    *,
    minutes: int = 0,
    run_id: str = "run-authobs-001",
) -> TimestampOrder:
    return TimestampOrder(
        timestamp=(
            datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)
            + timedelta(minutes=minutes)
        ),
        run_id=run_id,
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

    lineage = AuthorityDecisionLineageChecker().trace(
        (grant, revoke, expiry),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

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

    lineage = AuthorityDecisionLineageChecker().trace(
        (denial,),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

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
        AuthorityDecisionLineageChecker().trace(
            (revoke, grant),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


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
        AuthorityDecisionLineageChecker().trace(
            (_grant(), revoke),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


def test_lineage_rejects_duplicate_decision_or_order_identity() -> None:
    grant = _grant()
    with pytest.raises(ValueError, match="decision identities"):
        AuthorityDecisionLineageChecker().trace(
            (grant, grant),
            context_state=AuthorityLineageContextState.COMPLETE,
        )

    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        1,
    )
    with pytest.raises(AuthorityDecisionOrderError, match="ordering identities"):
        AuthorityDecisionLineageChecker().trace(
            (grant, revoke),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


@pytest.mark.parametrize(
    "terminal_kind",
    (AuthorityDecisionKind.REVOKE, AuthorityDecisionKind.EXPIRY),
)
def test_terminal_timestamp_must_be_after_its_referenced_grant(
    terminal_kind: AuthorityDecisionKind,
) -> None:
    future_grant = _grant().model_copy(
        update={"timestamp_order": _order(50, minutes=50)}
    )
    past_terminal = _decision(
        terminal_kind,
        f"{terminal_kind.value.lower()}-decision-001",
        1,
        timestamp_order=_order(1, minutes=-50),
    )

    with pytest.raises(AuthorityDecisionOrderError, match="causally later"):
        AuthorityDecisionLineageChecker().trace(
            (future_grant, past_terminal),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


def test_equal_timestamp_from_different_runs_is_causally_ambiguous() -> None:
    grant = _grant().model_copy(
        update={"timestamp_order": _order(1, run_id="run-authobs-a")}
    )
    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        2,
        timestamp_order=_order(2, run_id="run-authobs-b"),
    )

    with pytest.raises(AuthorityDecisionOrderError, match="causally later"):
        AuthorityDecisionLineageChecker().trace(
            (grant, revoke),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


def test_multiple_grants_keep_terminal_references_separate() -> None:
    grant_a = _grant()
    grant_b = _decision(
        AuthorityDecisionKind.GRANT,
        "grant-decision-002",
        2,
    )
    revoke_b = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-002",
        3,
        grant_decision_id="grant-decision-002",
    )

    lineage = AuthorityDecisionLineageChecker().trace(
        (grant_a, grant_b, revoke_b),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

    assert lineage.decision_ids == (
        "grant-decision-001",
        "grant-decision-002",
        "revoke-decision-002",
    )

    wrong_grant = revoke_b.model_copy(
        update={"grant_decision_id": "grant-decision-missing"}
    )
    with pytest.raises(MissingGrantLineageError):
        AuthorityDecisionLineageChecker().trace(
            (grant_a, grant_b, wrong_grant),
            context_state=AuthorityLineageContextState.COMPLETE,
        )


def test_grant_consumption_evidence_binds_arc_c12_without_executing() -> None:
    lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(),),
        context_state=AuthorityLineageContextState.COMPLETE,
    )
    binding = GrantConsumptionEvidenceChecker().bind(lineage, _consumption())

    assert binding.referenced_decision is not None
    assert binding.referenced_decision.kind is AuthorityDecisionKind.GRANT
    assert binding.consumption.grant_consumer_identity == "ARC-C12"
    assert binding.consumption.harness_effect_execution_performed is False
    assert binding.grant_state is ObservedGrantState.ACTIVE
    assert binding.temporal_validity is ConsumptionTemporalValidity.VALID
    assert binding.lineage_bound is True


def test_consumption_selects_the_exact_grant_in_a_multiple_grant_lineage() -> None:
    grant_a = _grant()
    grant_b = _decision(
        AuthorityDecisionKind.GRANT,
        "grant-decision-002",
        2,
    )
    revoke_a = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        3,
        grant_decision_id="grant-decision-001",
    )
    lineage = AuthorityDecisionLineageChecker().trace(
        (grant_a, grant_b, revoke_a),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

    active_binding = GrantConsumptionEvidenceChecker().bind(
        lineage,
        _consumption(
            consumption_observation_id="grant-consumption-002",
            grant_decision_id="grant-decision-002",
            timestamp_order=_order(4),
        ),
    )
    revoked_binding = GrantConsumptionEvidenceChecker().bind(
        lineage,
        _consumption(timestamp_order=_order(4)),
    )

    assert active_binding.referenced_decision == grant_b
    assert active_binding.grant_state is ObservedGrantState.ACTIVE
    assert active_binding.lineage_bound is True
    assert revoked_binding.referenced_decision == grant_a
    assert revoked_binding.grant_state is ObservedGrantState.REVOKED
    assert revoked_binding.lineage_bound is False


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
        lineage = AuthorityDecisionLineageChecker().trace(
            (_grant(),),
            context_state=AuthorityLineageContextState.COMPLETE,
        )
        GrantConsumptionEvidenceChecker().bind(lineage, consumption)


def test_grant_consumption_rejects_wrong_role_and_marks_deny_non_consumable() -> None:
    with pytest.raises(ValidationError):
        _consumption(grant_consumer_identity="ARC-C04")

    denial = _decision(
        AuthorityDecisionKind.DENY,
        "deny-decision-001",
        1,
    )
    denial_lineage = AuthorityDecisionLineageChecker().trace(
        (denial,),
        context_state=AuthorityLineageContextState.COMPLETE,
    )
    denial_consumption = _consumption(
        grant_decision_id="deny-decision-001",
    )
    denied_binding = GrantConsumptionEvidenceChecker().bind(
        denial_lineage,
        denial_consumption,
    )
    assert denied_binding.grant_state is ObservedGrantState.DENIED
    assert denied_binding.temporal_validity is ConsumptionTemporalValidity.INVALID
    assert denied_binding.lineage_bound is False

    early_consumption = _consumption(timestamp_order=_order(0))
    active_lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(),),
        context_state=AuthorityLineageContextState.COMPLETE,
    )
    binding = GrantConsumptionEvidenceChecker().bind(
        active_lineage,
        early_consumption,
    )
    assert binding.temporal_validity is ConsumptionTemporalValidity.INVALID
    assert binding.lineage_bound is False


@pytest.mark.parametrize(
    ("terminal_kind", "expected_state"),
    (
        (AuthorityDecisionKind.REVOKE, ObservedGrantState.REVOKED),
        (AuthorityDecisionKind.EXPIRY, ObservedGrantState.EXPIRED),
    ),
)
def test_terminalized_grant_cannot_produce_affirmative_consumption_binding(
    terminal_kind: AuthorityDecisionKind,
    expected_state: ObservedGrantState,
) -> None:
    terminal = _decision(
        terminal_kind,
        f"{terminal_kind.value.lower()}-decision-001",
        2,
    )
    lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(), terminal),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

    binding = GrantConsumptionEvidenceChecker().bind(
        lineage,
        _consumption(timestamp_order=_order(3)),
    )

    assert binding.grant_state is expected_state
    assert binding.temporal_validity is ConsumptionTemporalValidity.INVALID
    assert binding.lineage_bound is False


def test_terminal_after_consumption_does_not_retroactively_invalidate_it() -> None:
    later_revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        3,
    )
    lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(), later_revoke),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

    binding = GrantConsumptionEvidenceChecker().bind(
        lineage,
        _consumption(timestamp_order=_order(2)),
    )

    assert binding.grant_state is ObservedGrantState.ACTIVE
    assert binding.temporal_validity is ConsumptionTemporalValidity.VALID
    assert binding.lineage_bound is True


def test_terminal_at_same_order_as_consumption_fails_closed() -> None:
    revoke = _decision(
        AuthorityDecisionKind.REVOKE,
        "revoke-decision-001",
        2,
    )
    lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(), revoke),
        context_state=AuthorityLineageContextState.COMPLETE,
    )

    binding = GrantConsumptionEvidenceChecker().bind(
        lineage,
        _consumption(timestamp_order=_order(2)),
    )

    assert binding.grant_state is ObservedGrantState.REVOKED
    assert binding.temporal_validity is ConsumptionTemporalValidity.INVALID
    assert binding.lineage_bound is False


@pytest.mark.parametrize(
    "context_state",
    (
        AuthorityLineageContextState.INCOMPLETE,
        AuthorityLineageContextState.UNKNOWN,
    ),
)
def test_incomplete_lineage_context_never_affirms_consumption(
    context_state: AuthorityLineageContextState,
) -> None:
    lineage = AuthorityDecisionLineageChecker().trace(
        (_grant(),),
        context_state=context_state,
    )

    binding = GrantConsumptionEvidenceChecker().bind(lineage, _consumption())

    assert binding.grant_state is ObservedGrantState.UNKNOWN
    assert binding.temporal_validity is ConsumptionTemporalValidity.UNKNOWN
    assert binding.lineage_bound is False


def test_legacy_consumption_binding_without_lineage_context_is_removed() -> None:
    with pytest.raises(TypeError, match="lineage evidence"):
        GrantConsumptionEvidenceChecker().bind(  # type: ignore[arg-type]
            _grant(),
            _consumption(),
        )

    with pytest.raises(TypeError):
        AuthorityDecisionLineageChecker().trace((_grant(),))  # type: ignore[call-arg]


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
