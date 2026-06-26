"""Tests para MemoryDecisionSink (slice 1b — sink de producción copia-digital).

Cubre:
  - Split A: shred del rationale no destruye el record_id ni el merkle_leaf_hash
  - ProvenanceWriteGate: rechaza si no hay merkle_leaf_hash (siempre tenemos uno → OK)
  - Recall tras escritura: el record aparece en el índice
  - Escritura idempotente: dos records con mismo id son upsert, no duplicados
  - Integración make_decider con ATLAS_DECISION_LOG=memory:<path>
  - Firewall D: MemoryDecisionSink no expone lectura del corpus de decisiones
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atlas.core.decider import (
    Allow,
    DecisionAction,
    MemoryDecisionSink,
    RecordingDecider,
    action_hash,
    make_decider,
)
from atlas.core.decider.decision_record import DecisionRecord
from atlas.core.decider.memory_decision_sink import _features_text, _merkle_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rec(
    action_kind: str = "test",
    verdict: str = "Allow",
    rationale: str | None = None,
    sensitivity: str = "normal",
) -> DecisionRecord:
    action = DecisionAction(kind=action_kind, descriptor="fn_x", mutating=False,
                             reversible=True, sensitivity=sensitivity)
    rid = action_hash(action, "intent")
    return DecisionRecord(
        record_id=rid,
        action_hash_val=rid,
        kind=action_kind,
        descriptor="fn_x",
        mutating=False,
        reversible=True,
        sensitivity=sensitivity,
        requires_approval=False,
        verdict=verdict,
        decider_name="TestDecider",
        decider_version="v1",
        timestamp_ns=1_000_000_000,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Escritura básica y recall
# ---------------------------------------------------------------------------

def test_record_appears_in_index(tmp_path: Path) -> None:
    sink = MemoryDecisionSink(tmp_path / "decisions.db")
    rec = _make_rec(rationale="auto approved")
    sink.record(rec)

    results = sink._idx.recall_all("test verdict Allow", k=5)
    ids = [r.lesson_id for r in results]
    assert rec.record_id in ids


def test_record_idempotent(tmp_path: Path) -> None:
    sink = MemoryDecisionSink(tmp_path / "decisions.db")
    rec = _make_rec()
    sink.record(rec)
    sink.record(rec)  # segunda escritura = upsert

    results = sink._idx.recall_all("test", k=10)
    ids = [r.lesson_id for r in results]
    assert ids.count(rec.record_id) == 1  # no duplicado


# ---------------------------------------------------------------------------
# Split A — shred del rationale no destruye el record_id ni el merkle
# ---------------------------------------------------------------------------

def test_shred_rationale_row_survives(tmp_path: Path) -> None:
    """Después del shred, el record_id sigue existible en el índice (row existe)."""
    sink = MemoryDecisionSink(tmp_path / "decisions.db")
    rec = _make_rec(rationale="confidential reasoning")
    sink.record(rec)

    # Shred: destruye el texto cifrado
    sink.shred_rationale(rec.record_id)

    # El record_id sigue presente en el índice (la fila existe, no fue borrada)
    # text_of levantará ShreddedContentError, pero la fila existe (merkle intacto)
    from atlas.memory.memory_index import ShreddedContentError
    with pytest.raises(ShreddedContentError):
        sink._idx.text_of(rec.record_id)


def test_merkle_hash_does_not_include_rationale() -> None:
    """El merkle_leaf_hash es idéntico con o sin rationale (hash sobre features)."""
    rec_with = _make_rec(rationale="some rationale")
    rec_without = _make_rec(rationale=None)
    # Ambos tienen el mismo record_id (misma acción), y el hash de features es igual
    assert _merkle_hash(rec_with) == _merkle_hash(rec_without)


def test_features_text_no_rationale() -> None:
    """_features_text no incluye el rationale."""
    rec = _make_rec(rationale="secret")
    features = _features_text(rec)
    assert "secret" not in features
    assert "verdict" in features
    assert "Allow" in features


# ---------------------------------------------------------------------------
# ProvenanceWriteGate: siempre tenemos merkle_leaf_hash → no rechaza
# ---------------------------------------------------------------------------

def test_provenance_write_gate_passes(tmp_path: Path) -> None:
    """MemoryDecisionSink siempre provee merkle_leaf_hash → ProvenanceWriteGate no rechaza."""
    sink = MemoryDecisionSink(tmp_path / "decisions.db")
    rec = _make_rec()
    # Si la gate rechazara, lanzaría WriteRejected; no debe lanzar nada
    sink.record(rec)  # no exception


# ---------------------------------------------------------------------------
# Firewall D: no expone API de lectura del corpus
# ---------------------------------------------------------------------------

def test_memory_sink_no_public_read_api(tmp_path: Path) -> None:
    sink = MemoryDecisionSink(tmp_path / "decisions.db")
    public_read_attrs = [
        a for a in dir(sink)
        if not a.startswith("_")
        and ("read" in a.lower() or "recall" in a.lower() or "get" in a.lower())
    ]
    assert not public_read_attrs, f"Unexpected public read API: {public_read_attrs}"


# ---------------------------------------------------------------------------
# Integración make_decider con ATLAS_DECISION_LOG=memory:<path>
# ---------------------------------------------------------------------------

def test_make_decider_memory_sink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setenv("ATLAS_DECISION_LOG", f"memory:{db_path}")
    decider = make_decider("human")
    assert isinstance(decider, RecordingDecider)
    assert isinstance(decider._sink, MemoryDecisionSink)


def test_make_decider_memory_sink_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Integración completa: decide() graba al SqliteMemoryIndex."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setenv("ATLAS_DECISION_LOG", f"memory:{db_path}")
    decider = make_decider("autonomous")

    action = DecisionAction(kind="route", descriptor="tool_safe", mutating=False,
                             reversible=True, sensitivity="normal")
    result = decider.decide(action, "test intent", {})
    assert isinstance(result, Allow)

    # Verifica que el registro llegó al índice
    sink: MemoryDecisionSink = decider._sink  # type: ignore[assignment]
    results = sink._idx.recall_all("route tool_safe", k=5)
    assert len(results) >= 1
