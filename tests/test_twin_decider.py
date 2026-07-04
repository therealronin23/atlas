"""Tests for TwinDecider (G0.9 Slice 2 + Slice 3)."""

from __future__ import annotations

import time

import pytest

from atlas.core.decider.decider import Allow, Deny, DecisionAction, RequiresHuman
from atlas.core.decider.decision_record import DecisionRecord, InMemoryDecisionSink
from atlas.core.decider.recording_decider import RecordingDecider
from atlas.core.decider.twin_decider import (
    MIN_CORPUS_SIZE,
    ShadowAccuracyLog,
    ShadowPredictor,
    TwinDecider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    kind: str = "file_edit",
    verdict: str = "Allow",
    mutating: bool = False,
    reversible: bool = True,
) -> DecisionRecord:
    return DecisionRecord(
        record_id=f"rec:{kind}:{verdict}:{time.monotonic_ns()}",
        action_hash_val="deadbeef",
        kind=kind,
        descriptor="",
        mutating=mutating,
        reversible=reversible,
        sensitivity="normal",
        requires_approval=False,
        verdict=verdict,
        decider_name="test",
        decider_version="v0",
        timestamp_ns=time.monotonic_ns(),
    )


def _make_corpus(
    n: int,
    kind: str = "file_edit",
    verdict: str = "Allow",
    mutating: bool = False,
    reversible: bool = True,
) -> list[DecisionRecord]:
    return [_make_record(kind=kind, verdict=verdict, mutating=mutating, reversible=reversible) for _ in range(n)]


class _StubDecider:
    """Decisor stub configurable para tests."""

    def __init__(self, verdict):
        self._verdict = verdict

    def decide(self, action, sanctioned_intent, context):
        return self._verdict


# ---------------------------------------------------------------------------
# Test 1: TwinDecider devuelve el veredicto del inner intacto
# ---------------------------------------------------------------------------

def test_twin_decider_returns_inner_verdict():
    inner = _StubDecider(Allow(reason="ok"))
    sink = InMemoryDecisionSink()
    twin = TwinDecider(inner, sink)

    action = DecisionAction(kind="file_edit")
    result = twin.decide(action, "intent", {})

    assert isinstance(result, Allow)
    assert result.reason == "ok"


def test_twin_decider_returns_deny_from_inner():
    inner = _StubDecider(Deny(reason="blocked"))
    sink = InMemoryDecisionSink()
    twin = TwinDecider(inner, sink)

    action = DecisionAction(kind="file_edit")
    result = twin.decide(action, "intent", {})

    assert isinstance(result, Deny)
    assert result.reason == "blocked"


def test_twin_decider_returns_requires_human_from_inner():
    inner = _StubDecider(RequiresHuman(reason="needs review"))
    sink = InMemoryDecisionSink()
    twin = TwinDecider(inner, sink)

    action = DecisionAction(kind="shell_exec")
    result = twin.decide(action, "intent", {})

    assert isinstance(result, RequiresHuman)


# ---------------------------------------------------------------------------
# Test 2: ShadowPredictor warmup — corpus < 30 → None
# ---------------------------------------------------------------------------

def test_shadow_predictor_warmup_returns_none():
    predictor = ShadowPredictor()
    corpus = _make_corpus(MIN_CORPUS_SIZE - 1, verdict="Allow")
    action = DecisionAction(kind="file_edit")

    result = predictor.predict(action, corpus)

    assert result is None


def test_shadow_predictor_exactly_at_threshold():
    predictor = ShadowPredictor()
    # Exactly MIN_CORPUS_SIZE records → should predict
    corpus = _make_corpus(MIN_CORPUS_SIZE, verdict="Allow")
    action = DecisionAction(kind="file_edit")

    result = predictor.predict(action, corpus)

    assert result == "Allow"


# ---------------------------------------------------------------------------
# Test 3: ShadowPredictor majority vote
# ---------------------------------------------------------------------------

def test_shadow_predictor_majority_vote():
    predictor = ShadowPredictor()
    # 35 Allow + 5 Deny = 40 total (≥ MIN_CORPUS_SIZE)
    corpus = (
        _make_corpus(35, verdict="Allow")
        + _make_corpus(5, verdict="Deny")
    )
    action = DecisionAction(kind="file_edit")

    result = predictor.predict(action, corpus)

    assert result == "Allow"


def test_shadow_predictor_minority_predicts_correctly():
    predictor = ShadowPredictor()
    # 31 Deny + 4 Allow → predicts Deny
    corpus = (
        _make_corpus(31, verdict="Deny")
        + _make_corpus(4, verdict="Allow")
    )
    action = DecisionAction(kind="file_edit")

    result = predictor.predict(action, corpus)

    assert result == "Deny"


def test_shadow_predictor_filters_human_resolution():
    predictor = ShadowPredictor()
    # 35 human_resolution records (should be excluded) + 5 real Allow
    human_records = _make_corpus(35, kind="human_resolution", verdict="Allow")
    real_records = _make_corpus(5, kind="file_edit", verdict="Deny")
    corpus = human_records + real_records

    action = DecisionAction(kind="file_edit")
    # total training = 5 (< MIN_CORPUS_SIZE) → None
    result = predictor.predict(action, corpus)

    assert result is None


# ---------------------------------------------------------------------------
# Test 4: TwinDecider accuracy_log tracks hits and misses
# ---------------------------------------------------------------------------

def test_twin_decider_accuracy_log_tracks_hits():
    # Build corpus: 32 Allow records for kind="file_edit"
    sink = InMemoryDecisionSink()
    sink.records = _make_corpus(32, kind="file_edit", verdict="Allow")

    # Inner returns Allow — should be a hit
    inner_allow = _StubDecider(Allow())
    twin_allow = TwinDecider(inner_allow, sink)

    action = DecisionAction(kind="file_edit")
    twin_allow.decide(action, "intent", {})

    assert twin_allow.accuracy_log.total == 1
    assert twin_allow.accuracy_log.accuracy == 1.0

    # Inner returns Deny — should be a miss
    inner_deny = _StubDecider(Deny())
    twin_deny = TwinDecider(inner_deny, sink)
    twin_deny.decide(action, "intent", {})

    assert twin_deny.accuracy_log.total == 1
    assert twin_deny.accuracy_log.accuracy == 0.0


def test_twin_decider_no_prediction_when_below_warmup():
    sink = InMemoryDecisionSink()
    sink.records = _make_corpus(MIN_CORPUS_SIZE - 1, verdict="Allow")

    inner = _StubDecider(Allow())
    twin = TwinDecider(inner, sink)
    action = DecisionAction(kind="file_edit")
    twin.decide(action, "intent", {})

    # No prediction was made
    assert twin.accuracy_log.total == 0
    assert twin.accuracy_log.accuracy is None


# ---------------------------------------------------------------------------
# Test 5: RecordingDecider.record_human_verdict appends to sink
# ---------------------------------------------------------------------------

def test_record_human_verdict_appends_to_sink():
    inner = _StubDecider(RequiresHuman(reason="needs human"))
    sink = InMemoryDecisionSink()
    recorder = RecordingDecider(inner, sink)

    recorder.record_human_verdict("deadbeef1234", "Allow", reason="looks good")

    assert len(sink.records) == 1
    rec = sink.records[0]
    assert rec.kind == "human_resolution"
    assert rec.verdict == "Allow"
    assert rec.record_id == "human:deadbeef1234"
    assert rec.action_hash_val == "deadbeef1234"
    assert rec.rationale == "looks good"
    assert rec.decider_name == "human"


def test_record_human_verdict_deny():
    inner = _StubDecider(RequiresHuman())
    sink = InMemoryDecisionSink()
    recorder = RecordingDecider(inner, sink)

    recorder.record_human_verdict("abc123", "Deny")

    rec = sink.records[0]
    assert rec.verdict == "Deny"
    assert rec.rationale is None  # no reason provided


def test_record_human_verdict_best_effort_on_sink_failure():
    """record_human_verdict silently continues when sink raises."""
    class FailSink:
        def record(self, rec):
            raise RuntimeError("disk full")

    inner = _StubDecider(RequiresHuman())
    recorder = RecordingDecider(inner, FailSink())

    # Should not raise
    recorder.record_human_verdict("xyz", "Allow")


# ---------------------------------------------------------------------------
# Test: ShadowAccuracyLog basics
# ---------------------------------------------------------------------------

def test_shadow_accuracy_log_empty():
    log = ShadowAccuracyLog()
    assert log.total == 0
    assert log.accuracy is None


def test_shadow_accuracy_log_accumulates():
    log = ShadowAccuracyLog()
    log.record("Allow", "Allow")
    log.record("Allow", "Allow")
    log.record("Deny", "Allow")

    assert log.total == 3
    assert abs(log.accuracy - 2 / 3) < 1e-9
