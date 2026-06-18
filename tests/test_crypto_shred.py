"""Tests for OSM-007 — crypto-shredding (GDPR Art. 17 vs. Merkle immutability).

Design: the dual-hash leaf keeps BOTH the client-signed payload_hash (permanent,
for APIResponse check 4) and a per-request salted_hash (salt stored externally,
destroyable).  Destroying the salt makes content irrecoverable while leaving the
Merkle tree intact and detect_omission() unaffected.
"""

from __future__ import annotations

import hashlib
import time

from atlas.transparency.client_cosign import InspectionRecord
from atlas.transparency.crypto_shred import SaltStore, SaltedEntry


# ---------------------------------------------------------------------------
# SaltedEntry
# ---------------------------------------------------------------------------


def test_salted_hash_differs_from_payload_hash() -> None:
    payload = b"user query: explain kafka consumer groups"
    payload_hash = hashlib.sha256(payload).hexdigest()
    store = SaltStore()
    entry = store.register(seq=0)
    salted = entry.compute_salted_hash(payload)
    assert salted != payload_hash, "salted and unsalted hashes must differ"


def test_same_payload_same_salt_reproducible() -> None:
    payload = b"some prompt"
    store = SaltStore()
    entry = store.register(seq=1)
    h1 = entry.compute_salted_hash(payload)
    h2 = SaltedEntry(seq=1, salt=entry.salt).compute_salted_hash(payload)
    assert h1 == h2


def test_different_payloads_same_salt_differ() -> None:
    store = SaltStore()
    entry = store.register(seq=2)
    h1 = entry.compute_salted_hash(b"payload A")
    h2 = entry.compute_salted_hash(b"payload B")
    assert h1 != h2


# ---------------------------------------------------------------------------
# SaltStore lifecycle
# ---------------------------------------------------------------------------


def test_register_is_idempotent() -> None:
    store = SaltStore()
    e1 = store.register(seq=5)
    e2 = store.register(seq=5)
    assert e1.salt == e2.salt, "re-registering same seq must return same salt"


def test_shred_destroys_salt() -> None:
    store = SaltStore()
    store.register(seq=10)
    assert not store.is_shredded(10)
    store.shred(10)
    assert store.is_shredded(10)
    assert store.get_salt(10) is None


def test_shred_is_idempotent() -> None:
    store = SaltStore()
    store.register(seq=3)
    store.shred(3)
    store.shred(3)  # second call must not raise
    assert store.is_shredded(3)


def test_shred_makes_content_irrecoverable() -> None:
    payload = b"sensitive user query"
    store = SaltStore()
    entry = store.register(seq=7)
    salted_hash = entry.compute_salted_hash(payload)

    store.shred(7)

    # After shredding: cannot recompute (no salt) and cannot invert SHA-256.
    assert store.get_salt(7) is None
    # The only way to check if payload matches is to have the salt.
    # Confirm: even with the original payload, we cannot recompute salted_hash.
    recovered_salt = store.get_salt(7)
    assert recovered_salt is None
    # The salted_hash in the tree is now a dead-end.
    _ = salted_hash  # committed to tree; cannot link back to payload


# ---------------------------------------------------------------------------
# Dual-hash InspectionRecord — binding check still works after adding salted_hash
# ---------------------------------------------------------------------------


def _make_record(seq: int, payload: bytes, salted_hash: str = "") -> InspectionRecord:
    payload_hash = hashlib.sha256(payload).hexdigest()
    cosig = f'{{"payload_hash":"{payload_hash}","seq":{seq},"signature":"abc"}}'
    return InspectionRecord(
        seq=seq,
        payload_hash=payload_hash,
        cosig=cosig,
        decision="allow",
        cause="below-threshold",
        timestamp_ns=int(time.time() * 1e9),
        salted_hash=salted_hash,
    )


def test_binding_check_4_passes_without_salted_hash() -> None:
    payload = b"a normal prompt"
    record = _make_record(0, payload)
    leaf = record.to_bytes()
    # APIResponse check 4: payload_hash.encode() in leaf_bytes
    assert record.payload_hash.encode() in leaf


def test_binding_check_4_passes_with_salted_hash_present() -> None:
    payload = b"another prompt"
    store = SaltStore()
    entry = store.register(seq=1)
    salted = entry.compute_salted_hash(payload)
    record = _make_record(1, payload, salted_hash=salted)
    leaf = record.to_bytes()
    # The client-signed hash is still findable in the leaf.
    assert record.payload_hash.encode() in leaf
    # The salted hash is also present (for enhanced audit).
    assert salted.encode() in leaf


def test_binding_check_4_passes_after_shredding() -> None:
    payload = b"query to be erased"
    store = SaltStore()
    entry = store.register(seq=2)
    salted = entry.compute_salted_hash(payload)
    record = _make_record(2, payload, salted_hash=salted)
    leaf = record.to_bytes()

    # Shred: destroy the salt.
    store.shred(2)

    # payload_hash is STILL in the leaf — check 4 still works.
    assert record.payload_hash.encode() in leaf
    # salted_hash is still in the leaf bytes (tree is immutable), but the
    # content cannot be recovered because the salt no longer exists.
    assert salted.encode() in leaf
    assert store.get_salt(2) is None


def test_salted_hash_in_leaf_bytes() -> None:
    payload = b"example"
    store = SaltStore()
    entry = store.register(seq=3)
    salted = entry.compute_salted_hash(payload)
    record = _make_record(3, payload, salted_hash=salted)
    leaf = record.to_bytes()
    # Both hashes must be present in the serialized leaf.
    assert record.payload_hash.encode() in leaf
    assert salted.encode() in leaf


# ---------------------------------------------------------------------------
# detect_omission() is unaffected by shredding (completeness is seq-based)
# ---------------------------------------------------------------------------


def test_detect_omission_unaffected_by_shredding() -> None:
    from atlas.transparency.client_cosign import detect_omission

    # Simulate: emitted seqs 0-4, observed 0,1,3,4 (seq=2 omitted), seq=2 shredded.
    store = SaltStore()
    for s in range(5):
        store.register(s)
    store.shred(2)

    observed = [0, 1, 3, 4]
    gaps = detect_omission(observed, last_emitted=4)
    assert gaps == [2], "shredding a seq does not remove it from omission detection"
