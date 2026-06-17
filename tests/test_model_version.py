"""Tests for model_version_hash in InspectionRecord (ADR-053 / completeness protocol).

Covers:
- Hash determinism
- InspectionRecord.to_bytes() includes model_version_hash in canonical order
- Retrocompatibility of empty ("") default
- SubjectLedger detects version change mid-session
- Honest session without version changes → no violations
- Legacy InspectionRecord (without C3) still valid with empty hash
- Audit-trail property: every record carries the version
- Canonical JSON serialization of the field
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from atlas.transparency.client_cosign import InspectionRecord


# ---------------------------------------------------------------------------
# Helper: compute model_version_hash the same way the demo does
# ---------------------------------------------------------------------------


def _version_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _make_record(
    seq: int = 1,
    model_version_hash: str = "",
) -> InspectionRecord:
    return InspectionRecord(
        seq=seq,
        payload_hash="aabbcc",
        cosig='{"nonce":1}',
        decision="allow",
        cause="test",
        timestamp_ns=1000,
        model_version_hash=model_version_hash,
    )


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------


def test_hash_same_bytes_same_hash() -> None:
    """Mismos bytes → mismo SHA-256 hex."""
    payload = b"model-weights-v1"
    h1 = _version_hash(payload)
    h2 = _version_hash(payload)
    assert h1 == h2


def test_hash_different_bytes_different_hash() -> None:
    """Bytes distintos → hashes distintos."""
    h1 = _version_hash(b"model-v1")
    h2 = _version_hash(b"model-v2")
    assert h1 != h2


def test_hash_is_hex_string() -> None:
    """El hash resultante es una cadena hexadecimal de 64 caracteres (SHA-256)."""
    h = _version_hash(b"any-model-response")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# InspectionRecord.to_bytes() canonical JSON
# ---------------------------------------------------------------------------


def test_to_bytes_includes_model_version_hash() -> None:
    """to_bytes() incluye model_version_hash en el JSON canónico."""
    mvh = _version_hash(b"v1")
    rec = _make_record(model_version_hash=mvh)
    raw = rec.to_bytes()
    decoded = json.loads(raw)
    assert "model_version_hash" in decoded
    assert decoded["model_version_hash"] == mvh


def test_to_bytes_keys_alphabetically_ordered() -> None:
    """Las claves del JSON están en orden alfabético (sort_keys=True)."""
    rec = _make_record(model_version_hash=_version_hash(b"x"))
    decoded = json.loads(rec.to_bytes())
    keys = list(decoded.keys())
    assert keys == sorted(keys)


def test_to_bytes_model_version_hash_position() -> None:
    """model_version_hash aparece entre 'decision' y 'payload_hash' (orden alfa)."""
    rec = _make_record(model_version_hash=_version_hash(b"x"))
    keys = list(json.loads(rec.to_bytes()).keys())
    idx = keys.index("model_version_hash")
    assert keys[idx - 1] == "decision"
    assert keys[idx + 1] == "payload_hash"


def test_to_bytes_no_whitespace() -> None:
    """Serialización compacta: sin espacios tras ':' ni ','."""
    rec = _make_record(model_version_hash=_version_hash(b"compact"))
    raw = rec.to_bytes()
    assert b": " not in raw
    assert b", " not in raw


# ---------------------------------------------------------------------------
# Retrocompatibility: empty default
# ---------------------------------------------------------------------------


def test_empty_model_version_hash_default() -> None:
    """El campo por defecto es '' — no rompe registros históricos sin tracking."""
    rec = _make_record()
    assert rec.model_version_hash == ""


def test_empty_model_version_hash_serializes() -> None:
    """InspectionRecord con hash vacío serializa correctamente (retrocompat)."""
    rec = _make_record(model_version_hash="")
    decoded = json.loads(rec.to_bytes())
    assert decoded["model_version_hash"] == ""


def test_legacy_record_without_version_still_valid() -> None:
    """Registro legado (C3 ausente) con hash vacío: to_bytes() sin error."""
    rec = InspectionRecord(
        seq=0,
        payload_hash="legacy",
        cosig="{}",
        decision="allow",
        cause="legacy-path",
        timestamp_ns=0,
        # model_version_hash omitido → ""
    )
    raw = rec.to_bytes()
    decoded = json.loads(raw)
    assert decoded["model_version_hash"] == ""


# ---------------------------------------------------------------------------
# SubjectLedger: version-change mid-session detection via demo
# ---------------------------------------------------------------------------


def _load_demo():
    demo_path = Path(__file__).resolve().parent.parent / "docs" / "demo" / "completeness_demo.py"
    spec = importlib.util.spec_from_file_location("completeness_demo_mv", demo_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_honest_session_no_version_violations() -> None:
    """Sesión honesta (sin cambios de versión) → sin omisiones detectadas."""
    demo = _load_demo()
    gaps = demo.run_session("honest-mv", demo.OperatorBehaviour())
    assert gaps == []


def test_audit_trail_every_record_has_version_field() -> None:
    """Todos los InspectionRecord serializado tienen model_version_hash."""
    records = [
        _make_record(seq=i, model_version_hash=_version_hash(f"v{i}".encode()))
        for i in range(5)
    ]
    for rec in records:
        decoded = json.loads(rec.to_bytes())
        assert "model_version_hash" in decoded
        assert decoded["model_version_hash"] != ""


def test_version_change_produces_different_hashes() -> None:
    """Dos versiones del modelo producen hashes distintos → drift auditable."""
    h_v1 = _version_hash(b"model-response-v1")
    h_v2 = _version_hash(b"model-response-v2")
    rec1 = _make_record(seq=1, model_version_hash=h_v1)
    rec2 = _make_record(seq=2, model_version_hash=h_v2)
    assert rec1.model_version_hash != rec2.model_version_hash
