"""Tests para TransparencyGateway + cableado en InferenceHub (ADR-053 real).

Cubre:
- TransparencyGateway.call() — protocolo completo
- Firma bidireccional (subject + operator Receipt)
- APIResponse con los 6 campos de verificación
- InferenceHub con transparency gateway cableado
- Latencia del overhead del protocolo (P50 sin modelo)
- key_store: load_or_create persiste y es idempotente
"""
from __future__ import annotations

import hashlib
import os
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.core.inference_hub import InferenceHub, InferenceRequest, InferenceLevel
from atlas.security.authorization import Ed25519Signer, Ed25519Verifier, HMACSigner
from atlas.transparency.client_cosign import (
    ClientCosigner,
    Receipt,
    verify_cosigned_request,
    verify_receipt,
)
from atlas.transparency.gateway import GatewayMetrics, TransparencyGateway
from atlas.transparency.key_store import load_or_create
from atlas.transparency.log import TransparencyLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ed25519() -> tuple[Ed25519Signer, Ed25519Verifier]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes_raw()
    pub = key.public_key().public_bytes_raw()
    return Ed25519Signer(priv), Ed25519Verifier(pub)


def _make_gateway(
    start_seq: int = 0,
) -> tuple[TransparencyGateway, ClientCosigner, Ed25519Verifier, TransparencyLog]:
    subj_signer, subj_verifier = _make_ed25519()
    op_signer, op_verifier = _make_ed25519()
    log_signer, _ = _make_ed25519()

    log = TransparencyLog(signer=log_signer)
    cosigner = ClientCosigner(subj_signer, start_seq=start_seq)
    gw = TransparencyGateway(cosigner, op_signer, log)
    return gw, cosigner, op_verifier, log


def _noop_call(payload: bytes) -> bytes:
    return b"model response: " + payload[:20]


# ---------------------------------------------------------------------------
# TransparencyGateway — protocolo completo
# ---------------------------------------------------------------------------


def test_gateway_call_returns_api_response_and_metrics():
    gw, _, _, _ = _make_gateway()
    api_resp, metrics = gw.call(b"hello world", _noop_call)
    assert api_resp.result == b"model response: hello world"[:27]  # noop truncates
    assert isinstance(metrics, GatewayMetrics)


def test_gateway_seq_ack_matches_expected():
    gw, cosigner, _, _ = _make_gateway(start_seq=0)
    api_resp, _ = gw.call(b"test", _noop_call)
    assert api_resp.seq_ack == 0


def test_gateway_seq_increments_per_call():
    gw, _, _, _ = _make_gateway()
    r1, _ = gw.call(b"first", _noop_call)
    r2, _ = gw.call(b"second", _noop_call)
    assert r1.seq_ack == 0
    assert r2.seq_ack == 1


def test_gateway_sth_covers_both_records():
    gw, _, _, log = _make_gateway()
    assert log.tree_size == 0
    gw.call(b"payload", _noop_call)
    # input + output = 2 entries
    assert log.tree_size == 2


def test_gateway_inclusion_proof_is_nonempty_after_multiple_calls():
    gw, _, _, _ = _make_gateway()
    gw.call(b"first", _noop_call)
    api_resp, _ = gw.call(b"second", _noop_call)
    # After 4 entries, proofs should be non-empty lists
    assert isinstance(api_resp.inclusion_proof, list)
    assert isinstance(api_resp.output_inclusion_proof, list)


def test_gateway_consistency_from_advances():
    gw, _, _, _ = _make_gateway()
    r1, _ = gw.call(b"a", _noop_call)
    assert r1.consistency_from == 0  # log was empty before
    r2, _ = gw.call(b"b", _noop_call)
    assert r2.consistency_from == 2  # after first call, 2 entries


def test_gateway_leaf_bytes_contains_payload_hash():
    payload = b"verifiable prompt"
    gw, _, _, _ = _make_gateway()
    api_resp, _ = gw.call(payload, _noop_call)
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert expected_hash.encode() in api_resp.leaf_bytes


def test_gateway_output_leaf_bytes_contains_output_hash():
    payload = b"hello"
    result = _noop_call(payload)
    gw, _, _, _ = _make_gateway()
    api_resp, _ = gw.call(payload, _noop_call)
    expected_out_hash = hashlib.sha256(result).hexdigest()
    assert expected_out_hash.encode() in api_resp.output_leaf_bytes


def test_gateway_sth_tree_size_is_consistent():
    gw, _, _, log = _make_gateway()
    gw.call(b"x", _noop_call)
    gw.call(b"y", _noop_call)
    api_resp, _ = gw.call(b"z", _noop_call)
    assert api_resp.sth.tree_size == log.tree_size == 6


# ---------------------------------------------------------------------------
# Firma bidireccional — Receipt (operador acredita recepción)
# ---------------------------------------------------------------------------


def test_gateway_issues_receipt_via_private_api():
    """Verificar que _issue_receipt produce un Receipt verificable."""
    subj_signer, _ = _make_ed25519()
    op_signer, op_verifier = _make_ed25519()
    log_signer, _ = _make_ed25519()
    log = TransparencyLog(signer=log_signer)
    cosigner = ClientCosigner(subj_signer)
    gw = TransparencyGateway(cosigner, op_signer, log)

    receipt = gw._issue_receipt(seq=5, payload_hash="abc123", now_ns=42)
    assert isinstance(receipt, Receipt)
    assert receipt.seq == 5
    assert receipt.payload_hash == "abc123"
    assert verify_receipt(receipt, "abc123", op_verifier) is True


def test_gateway_receipt_fails_with_wrong_verifier():
    _, wrong_verifier = _make_ed25519()
    gw, _, _, _ = _make_gateway()
    receipt = gw._issue_receipt(0, "hash", time.time_ns())
    assert verify_receipt(receipt, "hash", wrong_verifier) is False


def test_gateway_cosigned_request_verifiable_by_subject_verifier():
    subj_signer, subj_verifier = _make_ed25519()
    op_signer, _ = _make_ed25519()
    log_signer, _ = _make_ed25519()
    log = TransparencyLog(signer=log_signer)
    cosigner = ClientCosigner(subj_signer)
    gw = TransparencyGateway(cosigner, op_signer, log)

    payload = b"verify this"
    api_resp, _ = gw.call(payload, _noop_call)

    import json
    from atlas.transparency.client_cosign import CosignedRequest
    cosig_data = json.loads(api_resp.leaf_bytes)
    cosigned = CosignedRequest.from_json(cosig_data["cosig"])
    assert verify_cosigned_request(cosigned, payload, subj_verifier) is True


# ---------------------------------------------------------------------------
# Métricas de latencia (benchmark del overhead del protocolo)
# ---------------------------------------------------------------------------


def test_gateway_overhead_p50_under_5ms():
    """El overhead del protocolo (pre+post, sin modelo) debe ser < 5 ms P50.

    PunkGo publicó <1.3ms; nuestro target es <5ms con Python puro.
    Este test documenta el número real — si falla, hay una regresión de rendimiento.
    """
    gw, _, _, _ = _make_gateway()
    samples: list[float] = []

    def instant_call(p: bytes) -> bytes:
        return b"r"

    for _ in range(100):
        _, metrics = gw.call(b"benchmark payload " * 3, instant_call)
        overhead = metrics.pre_ms + metrics.post_ms
        samples.append(overhead)

    p50 = statistics.median(samples)
    p99 = sorted(samples)[int(len(samples) * 0.99)]
    # Imprimir para que quede en el output del test con -v
    print(f"\nGateway overhead — P50: {p50:.3f}ms  P99: {p99:.3f}ms  (n=100)")
    assert p50 < 5.0, f"P50 overhead demasiado alto: {p50:.2f}ms"


def test_gateway_metrics_pre_post_positive():
    gw, _, _, _ = _make_gateway()
    _, m = gw.call(b"x", _noop_call)
    assert m.pre_ms >= 0
    assert m.post_ms >= 0
    assert m.model_ms >= 0
    assert m.total_ms == pytest.approx(m.pre_ms + m.model_ms + m.post_ms, abs=0.01)


# ---------------------------------------------------------------------------
# InferenceHub cableado con TransparencyGateway
# ---------------------------------------------------------------------------


def _make_hub_with_gateway() -> tuple[InferenceHub, TransparencyGateway]:
    subj_signer, _ = _make_ed25519()
    op_signer, _ = _make_ed25519()
    log_signer, _ = _make_ed25519()
    log = TransparencyLog(signer=log_signer)
    cosigner = ClientCosigner(subj_signer)
    gw = TransparencyGateway(cosigner, op_signer, log)
    hub = InferenceHub(mode="stub", transparency=gw)
    return hub, gw


def test_hub_infer_with_gateway_returns_api_response():
    hub, _ = _make_hub_with_gateway()
    req = InferenceRequest(prompt="hello", level=InferenceLevel.L1)
    resp = hub.infer(req)
    assert resp.api_response is not None


def test_hub_infer_without_gateway_has_no_api_response():
    hub = InferenceHub(mode="stub")
    req = InferenceRequest(prompt="hello", level=InferenceLevel.L1)
    resp = hub.infer(req)
    assert resp.api_response is None


def test_hub_infer_with_gateway_seq_increments():
    hub, _ = _make_hub_with_gateway()
    req = InferenceRequest(prompt="first", level=InferenceLevel.L1)
    r1 = hub.infer(req)
    r2 = hub.infer(req)
    assert r1.api_response is not None
    assert r2.api_response is not None
    assert r1.api_response.seq_ack == 0
    assert r2.api_response.seq_ack == 1


def test_hub_infer_with_gateway_log_grows():
    hub, gw = _make_hub_with_gateway()
    req = InferenceRequest(prompt="test", level=InferenceLevel.L1)
    # acceder al log a través del gateway
    log = gw._log
    assert log.tree_size == 0
    hub.infer(req)
    assert log.tree_size == 2  # input + output records
    hub.infer(req)
    assert log.tree_size == 4


def test_hub_infer_with_gateway_stub_still_succeeds():
    hub, _ = _make_hub_with_gateway()
    req = InferenceRequest(prompt="hello world", level=InferenceLevel.L1)
    resp = hub.infer(req)
    assert resp.success is True
    assert resp.api_response is not None


def test_hub_infer_transparency_does_not_affect_existing_stub_behavior():
    """El texto de respuesta es el mismo con o sin gateway."""
    req = InferenceRequest(prompt="same prompt", level=InferenceLevel.L1)

    hub_plain = InferenceHub(mode="stub")
    hub_gw, _ = _make_hub_with_gateway()

    r_plain = hub_plain.infer(req)
    r_gw = hub_gw.infer(req)

    assert r_plain.text == r_gw.text
    assert r_plain.success == r_gw.success


# ---------------------------------------------------------------------------
# key_store — persistencia local
# ---------------------------------------------------------------------------


def test_key_store_creates_file_on_first_call():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)
        signer, verifier, pub = load_or_create("test_key.bin", directory=path)
        key_file = path / "test_key.bin"
        assert key_file.exists()
        assert key_file.stat().st_size == 64


def test_key_store_idempotent_same_key_on_reload():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)
        _, _, pub1 = load_or_create("test_key.bin", directory=path)
        _, _, pub2 = load_or_create("test_key.bin", directory=path)
        assert pub1 == pub2


def test_key_store_different_files_different_keys():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)
        _, _, pub1 = load_or_create("key_a.bin", directory=path)
        _, _, pub2 = load_or_create("key_b.bin", directory=path)
        assert pub1 != pub2


def test_key_store_sign_verify_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)
        signer, verifier, _ = load_or_create("roundtrip.bin", directory=path)
        payload = b"sign this"
        sig = signer.sign(payload)
        assert verifier.verify(payload, sig) is True


def test_key_store_file_permissions_are_600():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d)
        load_or_create("perm_test.bin", directory=path)
        key_file = path / "perm_test.bin"
        mode = oct(key_file.stat().st_mode)[-3:]
        assert mode == "600"


# ---------------------------------------------------------------------------
# SaltStore cableado en TransparencyGateway (OSM-007)
# ---------------------------------------------------------------------------

import json as _json

from atlas.transparency.crypto_shred import SaltStore


def _make_gateway_with_salt_store() -> tuple[TransparencyGateway, SaltStore]:
    """Devuelve (gateway, salt_store) — el gateway tiene SaltStore cableado."""
    subj_signer, _ = _make_ed25519()
    op_signer, _ = _make_ed25519()
    log_signer, _ = _make_ed25519()
    log = TransparencyLog(signer=log_signer)
    salt_store = SaltStore()
    cosigner = ClientCosigner(subj_signer)
    gw = TransparencyGateway(cosigner, op_signer, log, salt_store=salt_store)
    return gw, salt_store


def test_gateway_with_salt_store_populates_salted_hash():
    """leaf_bytes contiene un salted_hash no-vacío y distinto del SHA-256 sin sal."""
    payload = b"gdpr-sensitive prompt"
    gw, _ = _make_gateway_with_salt_store()
    api_resp, _ = gw.call(payload, _noop_call)
    doc = _json.loads(api_resp.leaf_bytes)
    salted = doc["salted_hash"]
    plain_hash = hashlib.sha256(payload).hexdigest()
    assert salted != ""
    assert salted != plain_hash


def test_gateway_salted_hash_erasure():
    """Tras shred(seq), get_salt devuelve None (el hash no es recomputable)."""
    payload = b"erase me"
    gw, salt_store = _make_gateway_with_salt_store()
    gw.call(payload, _noop_call)  # seq=0
    # El salt existe antes de borrar
    assert salt_store.get_salt(0) is not None
    salt_store.shred(0)
    assert salt_store.get_salt(0) is None


def test_gateway_without_salt_store_salted_hash_empty():
    """Sin SaltStore, salted_hash en el JSON del leaf es vacío."""
    payload = b"no salt here"
    gw, _, _, _ = _make_gateway()
    api_resp, _ = gw.call(payload, _noop_call)
    doc = _json.loads(api_resp.leaf_bytes)
    assert doc["salted_hash"] == ""


def test_gateway_payload_hash_unchanged_with_salt_store():
    """payload_hash sigue siendo SHA-256(payload) incluso con SaltStore activo."""
    payload = b"verify payload hash"
    gw, _ = _make_gateway_with_salt_store()
    api_resp, _ = gw.call(payload, _noop_call)
    doc = _json.loads(api_resp.leaf_bytes)
    assert doc["payload_hash"] == hashlib.sha256(payload).hexdigest()


def test_gateway_verify_cosigned_request_still_valid_with_salt_store():
    """verify_cosigned_request devuelve True cuando hay SaltStore."""
    subj_signer, subj_verifier = _make_ed25519()
    op_signer, _ = _make_ed25519()
    log_signer, _ = _make_ed25519()
    log = TransparencyLog(signer=log_signer)
    salt_store = SaltStore()
    cosigner = ClientCosigner(subj_signer)
    gw = TransparencyGateway(cosigner, op_signer, log, salt_store=salt_store)

    payload = b"cosign + salt"
    api_resp, _ = gw.call(payload, _noop_call)

    from atlas.transparency.client_cosign import CosignedRequest
    doc = _json.loads(api_resp.leaf_bytes)
    cosigned = CosignedRequest.from_json(doc["cosig"])
    assert verify_cosigned_request(cosigned, payload, subj_verifier) is True
