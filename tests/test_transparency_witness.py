"""Tests for ADR-053 T6 — Witness / split-view detection.

Covers:
  - observe() rejects STH with invalid signature (InvalidSignatureError).
  - detect_split_view() returns True for two inconsistent STHs with the same tree_size.
  - detect_split_view() returns False for identical / consistent STHs.
  - observe() raises SplitViewError when a second contradictory STH arrives.
  - observe() is idempotent for duplicate consistent STHs.
"""

from __future__ import annotations

import pytest

from atlas.security.authorization import HMACSigner, HMACVerifier
from atlas.transparency.log import SignedTreeHead, TransparencyLog
from atlas.transparency.witness import (
    InvalidSignatureError,
    SplitViewError,
    Witness,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SECRET = b"witness-test-secret"


@pytest.fixture()
def signer() -> HMACSigner:
    return HMACSigner(SECRET)


@pytest.fixture()
def verifier() -> HMACVerifier:
    return HMACVerifier(SECRET)


@pytest.fixture()
def witness(verifier: HMACVerifier) -> Witness:
    return Witness(sig_verifier=verifier)


def make_log_with_entries(signer: HMACSigner, entries: list[bytes]) -> TransparencyLog:
    log = TransparencyLog(signer=signer)
    for e in entries:
        log.append(e)
    return log


# ---------------------------------------------------------------------------
# observe() — signature validation
# ---------------------------------------------------------------------------


class TestObserveSignatureValidation:
    def test_valid_sth_is_accepted(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        log = make_log_with_entries(signer, [b"entry-1"])
        sth = log.signed_tree_head(timestamp=1_000_000)
        # Should not raise.
        witness.observe(sth)

    def test_tampered_signature_raises_invalid_signature_error(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        log = make_log_with_entries(signer, [b"entry-1"])
        sth = log.signed_tree_head(timestamp=1_000_000)
        # Tamper the signature.
        bad_sth = SignedTreeHead(
            tree_size=sth.tree_size,
            root_hash=sth.root_hash,
            timestamp=sth.timestamp,
            signature="deadbeef" * 8,  # wrong
            algo=sth.algo,
        )
        with pytest.raises(InvalidSignatureError):
            witness.observe(bad_sth)

    def test_wrong_key_raises_invalid_signature_error(
        self, signer: HMACSigner
    ) -> None:
        log = make_log_with_entries(signer, [b"entry-1"])
        sth = log.signed_tree_head(timestamp=1_000_000)
        # Verifier with a different key.
        wrong_verifier = HMACVerifier(b"completely-different-key")
        witness_wrong = Witness(sig_verifier=wrong_verifier)
        with pytest.raises(InvalidSignatureError):
            witness_wrong.observe(sth)


# ---------------------------------------------------------------------------
# detect_split_view() — pure structural detection
# ---------------------------------------------------------------------------


class TestDetectSplitView:
    def _make_sth(
        self,
        signer: HMACSigner,
        tree_size: int,
        root_hash: bytes,
        timestamp: int = 1_000_000,
    ) -> SignedTreeHead:
        """Build a properly-signed STH with an arbitrary root_hash."""
        draft = SignedTreeHead(
            tree_size=tree_size,
            root_hash=root_hash,
            timestamp=timestamp,
            signature="",
            algo=signer.algo,
        )
        sig = signer.sign(draft._payload())
        return SignedTreeHead(
            tree_size=tree_size,
            root_hash=root_hash,
            timestamp=timestamp,
            signature=sig,
            algo=signer.algo,
        )

    def test_same_tree_size_different_root_is_split_view(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        root_a = b"\xaa" * 32
        root_b = b"\xbb" * 32
        sth_a = self._make_sth(signer, tree_size=5, root_hash=root_a)
        sth_b = self._make_sth(signer, tree_size=5, root_hash=root_b)
        assert witness.detect_split_view(sth_a, sth_b) is True

    def test_same_tree_size_same_root_is_consistent(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        root = b"\xcc" * 32
        sth_a = self._make_sth(signer, tree_size=5, root_hash=root, timestamp=1)
        sth_b = self._make_sth(signer, tree_size=5, root_hash=root, timestamp=2)
        assert witness.detect_split_view(sth_a, sth_b) is False

    def test_different_tree_sizes_returns_false(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        root_a = b"\xaa" * 32
        root_b = b"\xbb" * 32
        sth_a = self._make_sth(signer, tree_size=3, root_hash=root_a)
        sth_b = self._make_sth(signer, tree_size=7, root_hash=root_b)
        assert witness.detect_split_view(sth_a, sth_b) is False


# ---------------------------------------------------------------------------
# observe() — conflict detection
# ---------------------------------------------------------------------------


class TestObserveSplitViewDetection:
    def _make_sth(
        self,
        signer: HMACSigner,
        tree_size: int,
        root_hash: bytes,
        timestamp: int = 1_000_000,
    ) -> SignedTreeHead:
        draft = SignedTreeHead(
            tree_size=tree_size,
            root_hash=root_hash,
            timestamp=timestamp,
            signature="",
            algo=signer.algo,
        )
        sig = signer.sign(draft._payload())
        return SignedTreeHead(
            tree_size=tree_size,
            root_hash=root_hash,
            timestamp=timestamp,
            signature=sig,
            algo=signer.algo,
        )

    def test_second_contradictory_sth_raises_split_view_error(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        sth_a = self._make_sth(signer, tree_size=10, root_hash=b"\xaa" * 32)
        sth_b = self._make_sth(signer, tree_size=10, root_hash=b"\xbb" * 32)
        witness.observe(sth_a)
        with pytest.raises(SplitViewError):
            witness.observe(sth_b)

    def test_duplicate_consistent_sth_is_idempotent(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        root = b"\xcc" * 32
        sth_a = self._make_sth(signer, tree_size=10, root_hash=root, timestamp=1)
        sth_b = self._make_sth(signer, tree_size=10, root_hash=root, timestamp=2)
        witness.observe(sth_a)
        # Should not raise even with different timestamp.
        witness.observe(sth_b)

    def test_different_tree_sizes_coexist(
        self, signer: HMACSigner, witness: Witness
    ) -> None:
        log = make_log_with_entries(signer, [b"e1"])
        sth_1 = log.signed_tree_head(timestamp=1)
        log.append(b"e2")
        sth_2 = log.signed_tree_head(timestamp=2)
        witness.observe(sth_1)
        witness.observe(sth_2)
