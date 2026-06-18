"""Tests for Layer 2 — output inspection completeness.

The symmetric counterpart to input inspection: the operator must also commit an
OutputInspectionRecord to the Merkle log before returning the model result.
The subject's checks 5 (output inclusion) and 6 (output binding) detect omissions.
"""

from __future__ import annotations

import hashlib
import json
import time

from atlas.transparency.client_cosign import OutputInspectionRecord


# ---------------------------------------------------------------------------
# OutputInspectionRecord structure
# ---------------------------------------------------------------------------


def _make_output_record(
    seq: int = 0,
    result: bytes = b"<model response>",
    decision: str = "allow",
    cause: str = "output-monitor: within policy",
) -> OutputInspectionRecord:
    return OutputInspectionRecord(
        seq=seq,
        output_hash=hashlib.sha256(result).hexdigest(),
        decision=decision,
        cause=cause,
        timestamp_ns=int(time.time() * 1e9),
    )


def test_output_hash_matches_result() -> None:
    result = b"the model's actual response"
    record = _make_output_record(result=result)
    expected = hashlib.sha256(result).hexdigest()
    assert record.output_hash == expected


def test_to_bytes_is_valid_json() -> None:
    record = _make_output_record(seq=3)
    doc = json.loads(record.to_bytes())
    assert doc["seq"] == 3
    assert doc["record_type"] == "output"
    assert "output_hash" in doc
    assert "decision" in doc
    assert "cause" in doc
    assert "timestamp_ns" in doc


def test_to_bytes_canonical_sort() -> None:
    record = _make_output_record(seq=1)
    raw = record.to_bytes().decode()
    keys = [k for k in json.loads(raw)]
    assert keys == sorted(keys), "JSON keys must be sorted for canonical serialisation"


def test_check_6_binding_passes() -> None:
    result = b"safe and correct response"
    record = _make_output_record(result=result)
    leaf = record.to_bytes()
    # Check 6: SHA-256(result).encode() in leaf_bytes
    assert hashlib.sha256(result).hexdigest().encode() in leaf


def test_check_6_binding_fails_on_substituted_result() -> None:
    result_inspected = b"original response"
    result_swapped = b"tampered response"
    record = _make_output_record(result=result_inspected)
    leaf = record.to_bytes()
    # Operator substitutes a different result after inspection.
    assert hashlib.sha256(result_swapped).hexdigest().encode() not in leaf


def test_different_results_produce_different_hashes() -> None:
    r1 = _make_output_record(result=b"response A")
    r2 = _make_output_record(result=b"response B")
    assert r1.output_hash != r2.output_hash


def test_decision_values_stored_correctly() -> None:
    for decision in ("allow", "block", "shadow_passive", "shadow_active"):
        record = _make_output_record(decision=decision)
        doc = json.loads(record.to_bytes())
        assert doc["decision"] == decision


def test_output_record_distinguishable_from_input_record() -> None:
    record = _make_output_record()
    doc = json.loads(record.to_bytes())
    assert doc.get("record_type") == "output"
    # Input records have "payload_hash" and "cosig"; output records do not.
    assert "payload_hash" not in doc
    assert "cosig" not in doc
    assert "output_hash" in doc


# ---------------------------------------------------------------------------
# Integration: output inspection in the Merkle log
# ---------------------------------------------------------------------------


def test_output_record_merkle_inclusion() -> None:
    """OutputInspectionRecord can be appended and proven in a TransparencyLog."""
    from atlas.security.authorization import Ed25519Signer
    from atlas.transparency.log import TransparencyLog
    from atlas.transparency.merkle_tree import verify_inclusion
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    signer = Ed25519Signer(priv_bytes)
    log = TransparencyLog(signer)

    result = b"model output"
    record = _make_output_record(seq=0, result=result)
    leaf = record.to_bytes()
    index = log.append(leaf)

    sth = log.signed_tree_head()
    proof = log.prove_inclusion(index)

    assert verify_inclusion(leaf, index, sth.tree_size, proof, sth.root_hash)
    # Check 6 binding passes on the committed leaf.
    assert hashlib.sha256(result).hexdigest().encode() in leaf


def test_output_omission_check_5_fails() -> None:
    """An empty inclusion proof for the output record fails check 5."""
    from atlas.transparency.merkle_tree import verify_inclusion

    record = _make_output_record(seq=2)
    leaf = record.to_bytes()
    bogus_root = b"\xff" * 32

    # Empty proof always fails verification.
    assert not verify_inclusion(leaf, 0, 1, [], bogus_root)
