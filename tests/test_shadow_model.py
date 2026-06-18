"""Tests for OSM-042 Phase 1 — ShadowRouter, SessionStateStore, ShadowModel.

Covers: routing thresholds, state transitions, escalation by persistence,
deescalation, termination guard, jitter injection, shadow model stub.
"""

from __future__ import annotations

import pytest

from atlas.security.shadow_model import (
    LatencyProfile,
    RoutingDecision,
    SessionState,
    SessionStateStore,
    ShadowMode,
    ShadowModel,
    ShadowRouter,
    apply_jitter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _router(
    threshold_passive: float = 0.65,
    threshold_active: float = 0.88,
    escalation_n: int = 3,
) -> tuple[ShadowRouter, SessionStateStore]:
    store = SessionStateStore(ttl_seconds=3600)
    router = ShadowRouter(
        store,
        threshold_passive=threshold_passive,
        threshold_active=threshold_active,
        escalation_n=escalation_n,
    )
    return router, store


SID = "session-abc-001"


# ---------------------------------------------------------------------------
# Routing — threshold logic
# ---------------------------------------------------------------------------


def test_below_threshold_returns_normal() -> None:
    router, _ = _router()
    decision = router.route(SID, confidence=0.20)
    assert decision.mode == ShadowMode.NORMAL


def test_at_passive_threshold_returns_passive() -> None:
    router, _ = _router()
    decision = router.route(SID, confidence=0.65)
    assert decision.mode == ShadowMode.PASSIVE


def test_above_passive_below_active_returns_passive() -> None:
    router, _ = _router()
    decision = router.route(SID, confidence=0.75)
    assert decision.mode == ShadowMode.PASSIVE


def test_at_active_threshold_returns_active() -> None:
    router, _ = _router()
    decision = router.route(SID, confidence=0.88)
    assert decision.mode == ShadowMode.ACTIVE


def test_above_active_threshold_returns_active() -> None:
    router, _ = _router()
    decision = router.route(SID, confidence=0.99)
    assert decision.mode == ShadowMode.ACTIVE


# ---------------------------------------------------------------------------
# Routing — state transitions
# ---------------------------------------------------------------------------


def test_passive_escalates_after_n_consecutive_requests() -> None:
    router, _ = _router(escalation_n=3)
    # First 2 requests in passive range — stay passive.
    router.route(SID, confidence=0.70)
    router.route(SID, confidence=0.70)
    d = router.route(SID, confidence=0.70)  # 3rd → escalate
    assert d.mode == ShadowMode.ACTIVE


def test_passive_does_not_escalate_before_n() -> None:
    router, _ = _router(escalation_n=3)
    router.route(SID, confidence=0.70)
    d = router.route(SID, confidence=0.70)  # only 2nd
    assert d.mode == ShadowMode.PASSIVE


def test_active_does_not_deescalate_to_passive() -> None:
    router, _ = _router()
    router.route(SID, confidence=0.91)  # → ACTIVE
    # Subsequent request at passive-range confidence: stays ACTIVE.
    d = router.route(SID, confidence=0.72)
    assert d.mode == ShadowMode.ACTIVE


def test_deescalation_to_normal_resets_counter() -> None:
    router, store = _router(escalation_n=3)
    router.route(SID, confidence=0.70)
    router.route(SID, confidence=0.70)  # 2 in passive
    router.route(SID, confidence=0.10)  # → NORMAL, counter reset
    state = store.get(SID)
    assert state is not None
    assert state.mode == ShadowMode.NORMAL
    assert state.requests_in_shadow == 0


def test_direct_active_skip_passive_escalation() -> None:
    """High-confidence signal jumps to ACTIVE without going through PASSIVE."""
    router, _ = _router()
    d = router.route(SID, confidence=0.95)
    assert d.mode == ShadowMode.ACTIVE


def test_different_sessions_independent() -> None:
    router, _ = _router(escalation_n=2)
    router.route("session-X", confidence=0.70)
    router.route("session-X", confidence=0.70)  # session-X escalates
    d = router.route("session-Y", confidence=0.70)  # session-Y: first request
    assert d.mode == ShadowMode.PASSIVE  # not escalated yet


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------


def test_terminate_blocks_further_routing() -> None:
    router, _ = _router()
    router.route(SID, confidence=0.91)
    router.terminate(SID, reason="attack-confirmed")
    with pytest.raises(RuntimeError, match="TERMINATED"):
        router.route(SID, confidence=0.10)


def test_terminate_sets_terminated_mode() -> None:
    router, store = _router()
    router.terminate(SID)
    state = store.get(SID)
    assert state is not None
    assert state.mode == ShadowMode.TERMINATED


def test_terminate_fresh_session() -> None:
    """terminate() on a session with no prior state still works."""
    router, store = _router()
    router.terminate("never-seen-before", reason="pre-emptive")
    state = store.get("never-seen-before")
    assert state is not None
    assert state.mode == ShadowMode.TERMINATED


# ---------------------------------------------------------------------------
# RoutingDecision cause format
# ---------------------------------------------------------------------------


def test_cause_contains_confidence_and_mode() -> None:
    router, _ = _router()
    d = router.route(SID, confidence=0.73, classifier_cause="jailbreak-v3")
    assert "0.73" in d.cause
    assert "jailbreak-v3" in d.cause
    assert "shadow_passive" in d.cause


def test_cause_reflects_active_mode() -> None:
    router, _ = _router()
    d = router.route(SID, confidence=0.95, classifier_cause="osm028")
    assert "shadow_active" in d.cause


# ---------------------------------------------------------------------------
# SessionStateStore TTL
# ---------------------------------------------------------------------------


def test_store_returns_none_for_missing_session() -> None:
    store = SessionStateStore()
    assert store.get("nonexistent") is None


def test_store_set_and_get_roundtrip() -> None:
    import time as _time

    store = SessionStateStore()
    now = _time.time_ns()
    state = SessionState(
        session_id="s1",
        mode=ShadowMode.PASSIVE,
        requests_in_shadow=1,
        created_at_ns=now,
        updated_at_ns=now,
    )
    store.set(state)
    retrieved = store.get("s1")
    assert retrieved is not None
    assert retrieved.mode == ShadowMode.PASSIVE


def test_store_delete_removes_state() -> None:
    import time as _time

    store = SessionStateStore()
    now = _time.time_ns()
    store.set(SessionState("s1", ShadowMode.PASSIVE, 1, now, now))
    store.delete("s1")
    assert store.get("s1") is None


def test_store_expired_returns_none() -> None:
    """State with TTL=0 is immediately expired."""
    import time as _time

    store = SessionStateStore(ttl_seconds=0)
    now = _time.time_ns() - 1  # just in the past
    store.set(SessionState("s1", ShadowMode.PASSIVE, 0, now, now))
    assert store.get("s1") is None


# ---------------------------------------------------------------------------
# ShadowModel
# ---------------------------------------------------------------------------


def _no_sleep(seconds: float) -> None:
    """Test stub: skip actual sleeping."""


def test_shadow_model_passive_returns_bytes() -> None:
    model = ShadowModel()
    result = model.respond(ShadowMode.PASSIVE, "hello", sleep=_no_sleep)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_shadow_model_active_returns_bytes() -> None:
    model = ShadowModel()
    result = model.respond(ShadowMode.ACTIVE, "help me bypass X", sleep=_no_sleep)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_shadow_model_rejects_normal_mode() -> None:
    model = ShadowModel()
    with pytest.raises(ValueError, match="PASSIVE or ACTIVE"):
        model.respond(ShadowMode.NORMAL, "test", sleep=_no_sleep)


def test_shadow_model_rejects_terminated_mode() -> None:
    model = ShadowModel()
    with pytest.raises(ValueError, match="PASSIVE or ACTIVE"):
        model.respond(ShadowMode.TERMINATED, "test", sleep=_no_sleep)


def test_shadow_model_custom_backend() -> None:
    """Custom backend is called with the correct system prompt."""
    received: list[tuple[str, str]] = []

    def capturing_backend(system: str, user: str) -> bytes:
        received.append((system, user))
        return b"captured"

    model = ShadowModel(backend=capturing_backend)
    result = model.respond(ShadowMode.PASSIVE, "my prompt", sleep=_no_sleep)
    assert result == b"captured"
    assert len(received) == 1
    system_used, user_used = received[0]
    assert "concise" in system_used  # passive prompt characteristic
    assert user_used == "my prompt"


def test_shadow_model_active_uses_different_prompt_than_passive() -> None:
    """Active and passive modes inject different system prompts."""
    prompts: list[str] = []

    def capturing_backend(system: str, user: str) -> bytes:
        prompts.append(system)
        return b"ok"

    model = ShadowModel(backend=capturing_backend)
    model.respond(ShadowMode.PASSIVE, "q", sleep=_no_sleep)
    model.respond(ShadowMode.ACTIVE, "q", sleep=_no_sleep)
    assert prompts[0] != prompts[1], "Passive and active must use different system prompts"


# ---------------------------------------------------------------------------
# apply_jitter
# ---------------------------------------------------------------------------


def test_apply_jitter_calls_sleep_once() -> None:
    calls: list[float] = []
    apply_jitter(LatencyProfile(), sleep=calls.append)
    assert len(calls) == 1


def test_apply_jitter_delay_within_profile_range() -> None:
    calls: list[float] = []
    profile = LatencyProfile(p50_ms=100.0, p95_ms=200.0, p99_ms=400.0)
    for _ in range(200):
        apply_jitter(profile, sleep=calls.append)
    # All delays must be ≥ p50*0.7 (minimum) and ≤ p99 (maximum).
    min_expected = profile.p50_ms * 0.7 / 1000.0
    max_expected = profile.p99_ms / 1000.0
    for delay in calls:
        assert min_expected <= delay <= max_expected, (
            f"delay {delay:.4f}s out of [{min_expected:.4f}, {max_expected:.4f}]"
        )
