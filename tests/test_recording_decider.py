"""Tests para RecordingDecider (slice 1 del arco copia-digital).

Cubre los invariantes de la spec y las correcciones del Cónclave:
  - Transparencia: verdict intacto para los 3 tipos
  - Un registro por decisión con features correctas
  - record_id == action_hash(action, intent)
  - Best-effort: sink fallido no rompe la decisión
  - Firewall D: corpus no influye en el veredicto (dos decisiones idénticas = mismo verdict)
  - decider_version presente y estable
  - Opt-in make_decider con ATLAS_DECISION_LOG
  - Sin ATLAS_DECISION_LOG → decider sin wrapper
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from atlas.core.decider import (
    Allow,
    DecisionAction,
    Decider,
    DecisionRecord,
    Deny,
    InMemoryDecisionSink,
    JsonlDecisionSink,
    RecordingDecider,
    RequiresHuman,
    Verdict,
    action_hash,
    make_decider,
)
from atlas.core.decider.decision_record import DecisionSink


# ---------------------------------------------------------------------------
# Fixtures / stubs
# ---------------------------------------------------------------------------

class _AllowDecider:
    def decide(self, action: DecisionAction, sanctioned_intent: str, context: Mapping[str, object]) -> Verdict:
        return Allow(reason="always allow")


class _DenyDecider:
    def decide(self, action: DecisionAction, sanctioned_intent: str, context: Mapping[str, object]) -> Verdict:
        return Deny(reason="always deny")


class _HumanDecider:
    def decide(self, action: DecisionAction, sanctioned_intent: str, context: Mapping[str, object]) -> Verdict:
        return RequiresHuman(reason="always ask human")


class _FailingSink:
    def record(self, rec: DecisionRecord) -> None:
        raise RuntimeError("sink broken")


def _action(kind: str = "test", sensitivity: str = "normal") -> DecisionAction:
    return DecisionAction(kind=kind, descriptor="tool_x", mutating=False, reversible=True, sensitivity=sensitivity)


# ---------------------------------------------------------------------------
# Transparencia: verdict intacto para los 3 tipos
# ---------------------------------------------------------------------------

def test_allow_passthrough() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
    result = rd.decide(_action(), "intent", {})
    assert isinstance(result, Allow)


def test_deny_passthrough() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_DenyDecider(), sink, decider_version="v1")
    result = rd.decide(_action(), "intent", {})
    assert isinstance(result, Deny)


def test_requires_human_passthrough() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_HumanDecider(), sink, decider_version="v1")
    result = rd.decide(_action(), "intent", {})
    assert isinstance(result, RequiresHuman)


# ---------------------------------------------------------------------------
# Un registro por decisión con features correctas
# ---------------------------------------------------------------------------

def test_record_features() -> None:
    sink = InMemoryDecisionSink()
    action = DecisionAction(kind="route", descriptor="fn_foo", mutating=True, reversible=False,
                             sensitivity="high", requires_approval=True)
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="abc123")
    rd.decide(action, "do something", {"rationale": "user approved"})

    assert len(sink.records) == 1
    rec = sink.records[0]
    assert rec.kind == "route"
    assert rec.descriptor == "fn_foo"
    assert rec.mutating is True
    assert rec.reversible is False
    assert rec.sensitivity == "high"
    assert rec.requires_approval is True
    assert rec.verdict == "Allow"
    assert rec.decider_name == "_AllowDecider"
    assert rec.decider_version == "abc123"
    assert rec.rationale == "user approved"


# ---------------------------------------------------------------------------
# record_id == action_hash(action, sanctioned_intent)
# ---------------------------------------------------------------------------

def test_record_id_equals_action_hash() -> None:
    sink = InMemoryDecisionSink()
    action = _action(kind="gate_f")
    intent = "run gate f"
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
    rd.decide(action, intent, {})

    expected = action_hash(action, intent)
    assert sink.records[0].record_id == expected
    assert sink.records[0].action_hash_val == expected


# ---------------------------------------------------------------------------
# Best-effort: sink fallido no rompe la decisión
# ---------------------------------------------------------------------------

def test_sink_failure_does_not_break_verdict() -> None:
    rd = RecordingDecider(_AllowDecider(), _FailingSink(), decider_version="v1")
    result = rd.decide(_action(), "intent", {})
    assert isinstance(result, Allow)  # decisión procede pese al fallo del sink


# ---------------------------------------------------------------------------
# Firewall D: corpus no influye en el veredicto
# (dos decisiones idénticas dan el MISMO verdict sin importar lo ya grabado)
# ---------------------------------------------------------------------------

def test_corpus_does_not_influence_verdict() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
    action = _action()
    intent = "same intent"

    # Primera decisión — graba al corpus
    v1 = rd.decide(action, intent, {})
    # Segunda decisión idéntica — el corpus ya tiene un registro
    v2 = rd.decide(action, intent, {})

    assert type(v1) is type(v2)  # mismo verdict, corpus ignorado
    assert len(sink.records) == 2  # dos registros, no uno (no deduplica)


# ---------------------------------------------------------------------------
# RecordingDecider no tiene API de lectura del corpus
# ---------------------------------------------------------------------------

def test_recording_decider_has_no_read_api() -> None:
    rd = RecordingDecider(_AllowDecider(), InMemoryDecisionSink(), decider_version="v1")
    # Exclude Python dunder/slot attrs; only check public interface
    read_attrs = [
        a for a in dir(rd)
        if not a.startswith("_")
        and ("read" in a.lower() or "recall" in a.lower() or "get" in a.lower())
    ]
    assert not read_attrs, f"Unexpected public read API: {read_attrs}"


# ---------------------------------------------------------------------------
# decider_version presente y estable para el mismo código
# ---------------------------------------------------------------------------

def test_decider_version_stable() -> None:
    sink1 = InMemoryDecisionSink()
    sink2 = InMemoryDecisionSink()
    # Dos instancias del mismo inner → misma version (derivada del código)
    rd1 = RecordingDecider(_AllowDecider(), sink1)
    rd2 = RecordingDecider(_AllowDecider(), sink2)
    rd1.decide(_action(), "i", {})
    rd2.decide(_action(), "i", {})
    assert sink1.records[0].decider_version == sink2.records[0].decider_version
    assert sink1.records[0].decider_version != ""


# ---------------------------------------------------------------------------
# Rationale captura el campo del contexto
# ---------------------------------------------------------------------------

def test_rationale_from_context() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
    rd.decide(_action(), "intent", {"rationale": "human said ok"})
    assert sink.records[0].rationale == "human said ok"


def test_rationale_none_when_absent() -> None:
    sink = InMemoryDecisionSink()
    rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
    rd.decide(_action(), "intent", {})
    assert sink.records[0].rationale is None


# ---------------------------------------------------------------------------
# JsonlDecisionSink: escribe al archivo correctamente
# ---------------------------------------------------------------------------

def test_jsonl_sink_writes_file() -> None:
    import json
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "decisions.jsonl"
        sink = JsonlDecisionSink(path)
        rd = RecordingDecider(_AllowDecider(), sink, decider_version="v1")
        rd.decide(_action(kind="route"), "my intent", {"rationale": "auto"})
        rd.decide(_action(kind="gate_f"), "other intent", {})

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        row0 = json.loads(lines[0])
        assert row0["kind"] == "route"
        assert row0["verdict"] == "Allow"
        assert row0["rationale"] == "auto"
        row1 = json.loads(lines[1])
        assert row1["kind"] == "gate_f"
        assert row1["rationale"] is None


# ---------------------------------------------------------------------------
# Opt-in make_decider con ATLAS_DECISION_LOG
# ---------------------------------------------------------------------------

def test_make_decider_wraps_with_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = str(tmp_path / "decisions.jsonl")
    monkeypatch.setenv("ATLAS_DECISION_LOG", log_path)
    decider = make_decider("human")
    assert isinstance(decider, RecordingDecider)


def test_make_decider_no_wrap_without_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DECISION_LOG", raising=False)
    decider = make_decider("human")
    assert not isinstance(decider, RecordingDecider)


def test_make_decider_autonomous_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from atlas.core.decider import AutonomousDecider
    log_path = str(tmp_path / "decisions.jsonl")
    monkeypatch.setenv("ATLAS_DECISION_LOG", log_path)
    decider = make_decider("autonomous")
    assert isinstance(decider, RecordingDecider)
    # pylint: disable=protected-access
    assert isinstance(decider._inner, AutonomousDecider)
