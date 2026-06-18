"""Tests for atlas.transparency.log — TransparencyLog + SignedTreeHead (T4 ADR-053)."""

from __future__ import annotations

import os

import pytest

from atlas.security.authorization import HMACSigner, HMACVerifier
from atlas.transparency.log import SignedTreeHead, TransparencyLog
from atlas.transparency.merkle_tree import (
    merkle_root,
    verify_consistency,
    verify_inclusion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY_A = b"key-alpha-32-bytes-padded-000000"
_KEY_B = b"key-bravo-32-bytes-padded-000000"


def _signer(key: bytes = _KEY_A) -> HMACSigner:
    return HMACSigner(key)


def _verifier(key: bytes = _KEY_A) -> HMACVerifier:
    return HMACVerifier(key)


# ---------------------------------------------------------------------------
# append — monotonic index
# ---------------------------------------------------------------------------


def test_append_returns_monotonic_indices() -> None:
    log = TransparencyLog(_signer())
    assert log.append(b"entry-0") == 0
    assert log.append(b"entry-1") == 1
    assert log.append(b"entry-2") == 2
    assert log.tree_size == 3


def test_tree_size_grows_monotonically() -> None:
    log = TransparencyLog(_signer())
    sizes = []
    for i in range(5):
        log.append(f"e{i}".encode())
        sizes.append(log.tree_size)
    assert sizes == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# STH — structure
# ---------------------------------------------------------------------------


def test_sth_tree_size_matches_log() -> None:
    log = TransparencyLog(_signer())
    log.append(b"a")
    log.append(b"b")
    sth = log.signed_tree_head()
    assert sth.tree_size == 2


def test_sth_root_hash_matches_merkle_root() -> None:
    entries = [b"x", b"y", b"z"]
    log = TransparencyLog(_signer())
    for e in entries:
        log.append(e)
    sth = log.signed_tree_head()
    assert sth.root_hash == merkle_root(entries)


def test_sth_timestamp_propagated() -> None:
    log = TransparencyLog(_signer())
    log.append(b"t")
    sth = log.signed_tree_head(timestamp=123456789)
    assert sth.timestamp == 123456789


def test_sth_algo_matches_signer() -> None:
    log = TransparencyLog(_signer())
    log.append(b"algo-check")
    sth = log.signed_tree_head()
    assert sth.algo == "hmac-sha256"


# ---------------------------------------------------------------------------
# STH — signature verification
# ---------------------------------------------------------------------------


def test_sth_verifies_with_correct_key() -> None:
    log = TransparencyLog(_signer(_KEY_A))
    log.append(b"hello")
    sth = log.signed_tree_head()
    assert sth.verify(_verifier(_KEY_A)) is True


def test_sth_fails_with_wrong_key() -> None:
    log = TransparencyLog(_signer(_KEY_A))
    log.append(b"hello")
    sth = log.signed_tree_head()
    assert sth.verify(_verifier(_KEY_B)) is False


# ---------------------------------------------------------------------------
# STH — tamper detection
# ---------------------------------------------------------------------------


def test_tampered_root_hash_fails_verification() -> None:
    log = TransparencyLog(_signer())
    log.append(b"real")
    sth = log.signed_tree_head()
    bad_root = bytes(b ^ 0xFF for b in sth.root_hash)
    tampered = SignedTreeHead(
        tree_size=sth.tree_size,
        root_hash=bad_root,
        timestamp=sth.timestamp,
        signature=sth.signature,
        algo=sth.algo,
    )
    assert tampered.verify(_verifier()) is False


def test_tampered_tree_size_fails_verification() -> None:
    log = TransparencyLog(_signer())
    log.append(b"real")
    sth = log.signed_tree_head()
    tampered = SignedTreeHead(
        tree_size=sth.tree_size + 1,
        root_hash=sth.root_hash,
        timestamp=sth.timestamp,
        signature=sth.signature,
        algo=sth.algo,
    )
    assert tampered.verify(_verifier()) is False


def test_tampered_timestamp_fails_verification() -> None:
    log = TransparencyLog(_signer())
    log.append(b"real")
    sth = log.signed_tree_head(timestamp=1_000_000)
    tampered = SignedTreeHead(
        tree_size=sth.tree_size,
        root_hash=sth.root_hash,
        timestamp=sth.timestamp + 1,
        signature=sth.signature,
        algo=sth.algo,
    )
    assert tampered.verify(_verifier()) is False


# ---------------------------------------------------------------------------
# prove_inclusion
# ---------------------------------------------------------------------------


def test_inclusion_proof_verifies_for_every_index() -> None:
    entries = [f"entry-{i}".encode() for i in range(7)]
    log = TransparencyLog(_signer())
    for e in entries:
        log.append(e)
    sth = log.signed_tree_head()
    for i, entry in enumerate(entries):
        proof = log.prove_inclusion(i)
        assert verify_inclusion(
            entry,
            i,
            sth.tree_size,
            proof,
            sth.root_hash,
        ), f"inclusion proof failed for index {i}"


def test_inclusion_proof_out_of_range_raises() -> None:
    log = TransparencyLog(_signer())
    log.append(b"only")
    with pytest.raises(IndexError):
        log.prove_inclusion(1)


def test_wrong_entry_fails_inclusion_verify() -> None:
    log = TransparencyLog(_signer())
    log.append(b"real")
    sth = log.signed_tree_head()
    proof = log.prove_inclusion(0)
    assert verify_inclusion(b"fake", 0, sth.tree_size, proof, sth.root_hash) is False


# ---------------------------------------------------------------------------
# prove_consistency
# ---------------------------------------------------------------------------


def test_consistency_proof_verifies_across_sizes() -> None:
    log = TransparencyLog(_signer())
    snapshots: list[tuple[int, bytes]] = []
    for i in range(8):
        log.append(f"e{i}".encode())
        sth = log.signed_tree_head()
        snapshots.append((sth.tree_size, sth.root_hash))

    # Every old snapshot should be consistent with the final tree.
    final_size, final_root = snapshots[-1]
    for old_size, old_root in snapshots[:-1]:
        proof = log.prove_consistency(old_size)
        assert verify_consistency(
            old_root, old_size, final_root, final_size, proof
        ), f"consistency proof failed from size {old_size} to {final_size}"


def test_consistency_proof_detects_rewrite() -> None:
    """A log that rewrites history produces an inconsistent root."""
    log1 = TransparencyLog(_signer())
    log1.append(b"original-entry")
    sth_old = log1.signed_tree_head()

    # Simulate a rewritten log (different first entry).
    log2 = TransparencyLog(_signer())
    log2.append(b"TAMPERED-entry")
    log2.append(b"second")
    proof = log2.prove_consistency(sth_old.tree_size)
    sth_new = log2.signed_tree_head()

    assert (
        verify_consistency(
            sth_old.root_hash, sth_old.tree_size, sth_new.root_hash, sth_new.tree_size, proof
        )
        is False
    )


def test_consistency_empty_to_nonempty() -> None:
    log = TransparencyLog(_signer())
    log.append(b"first")
    sth = log.signed_tree_head()
    proof = log.prove_consistency(0)
    # old_size=0 is always consistent (empty prefix), proof must be empty.
    assert proof == []
    assert verify_consistency(b"", 0, sth.root_hash, sth.tree_size, proof) is True


# ---------------------------------------------------------------------------
# No global state: two independent logs don't share state
# ---------------------------------------------------------------------------


def test_two_logs_are_independent() -> None:
    log_a = TransparencyLog(_signer())
    log_b = TransparencyLog(_signer())
    log_a.append(b"only-in-a")
    assert log_b.tree_size == 0
    sth_a = log_a.signed_tree_head()
    sth_b = log_b.signed_tree_head()
    assert sth_a.tree_size != sth_b.tree_size


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence_reloads_tree_size(tmp_path: "pytest.TempPathFactory") -> None:
    log_path = tmp_path / "log.bin"
    log1 = TransparencyLog(_signer(), path=log_path)
    for i in range(5):
        log1.append(f"entry-{i}".encode())
    log2 = TransparencyLog(_signer(), path=log_path)
    assert log2.tree_size == 5


def test_persistence_merkle_root_stable(tmp_path: "pytest.TempPathFactory") -> None:
    log_path = tmp_path / "log.bin"
    log1 = TransparencyLog(_signer(), path=log_path)
    for i in range(5):
        log1.append(f"entry-{i}".encode())
    root_before = log1.signed_tree_head(timestamp=0).root_hash
    log2 = TransparencyLog(_signer(), path=log_path)
    root_after = log2.signed_tree_head(timestamp=0).root_hash
    assert root_before == root_after


def test_persistence_first_append_continues_index(tmp_path: "pytest.TempPathFactory") -> None:
    log_path = tmp_path / "log.bin"
    log1 = TransparencyLog(_signer(), path=log_path)
    for i in range(5):
        log1.append(f"entry-{i}".encode())
    log2 = TransparencyLog(_signer(), path=log_path)
    idx = log2.append(b"new-entry")
    assert idx == 5


def test_persistence_binary_roundtrip(tmp_path: "pytest.TempPathFactory") -> None:
    log_path = tmp_path / "log.bin"
    raw = b"\x00\xff\n\r\x1b"
    log1 = TransparencyLog(_signer(), path=log_path)
    log1.append(raw)
    log2 = TransparencyLog(_signer(), path=log_path)
    assert log2._entries[0] == raw


def test_persistence_two_paths_independent(tmp_path: "pytest.TempPathFactory") -> None:
    path_a = tmp_path / "log_a.bin"
    path_b = tmp_path / "log_b.bin"
    log_a = TransparencyLog(_signer(), path=path_a)
    log_b = TransparencyLog(_signer(), path=path_b)
    for i in range(3):
        log_a.append(f"a-{i}".encode())
    log_b.append(b"b-only")
    # Reload each from its own path.
    reload_a = TransparencyLog(_signer(), path=path_a)
    reload_b = TransparencyLog(_signer(), path=path_b)
    assert reload_a.tree_size == 3
    assert reload_b.tree_size == 1
    assert reload_a._entries[0] == b"a-0"
    assert reload_b._entries[0] == b"b-only"


def test_persistence_no_file_without_path(tmp_path: "pytest.TempPathFactory") -> None:
    log = TransparencyLog(_signer())
    for i in range(3):
        log.append(f"entry-{i}".encode())
    assert list(tmp_path.iterdir()) == []
