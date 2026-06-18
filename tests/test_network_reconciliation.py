"""OSM-040 — receipt-based omission attribution under network failure.

Closes the plausible-deniability gap: a sequence gap can be either an operator
omission or a network failure. A signed receipt (operator admits receiving the
request) makes a subsequent missing inclusion an ATTRIBUTABLE omission — the
operator can no longer blame the network.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier
from atlas.transparency.client_cosign import (
    Receipt,
    attributable_omissions,
    verify_receipt,
)


def _keypair():
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = k.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return priv, pub


def _issue_receipt(signer: Ed25519Signer, seq: int, payload_hash: str,
                   received_at_ns: int = 1_000) -> Receipt:
    unsigned = Receipt(seq=seq, payload_hash=payload_hash,
                       received_at_ns=received_at_ns, signature="")
    return Receipt(seq=seq, payload_hash=payload_hash,
                   received_at_ns=received_at_ns,
                   signature=signer.sign(unsigned.signing_body()))


# ---------------------------------------------------------------------------
# Receipt verification
# ---------------------------------------------------------------------------


def test_valid_receipt_verifies():
    priv, pub = _keypair()
    r = _issue_receipt(Ed25519Signer(priv), seq=2, payload_hash="deadbeef")
    assert verify_receipt(r, "deadbeef", Ed25519Verifier(pub)) is True


def test_receipt_with_mismatched_hash_is_rejected():
    priv, pub = _keypair()
    r = _issue_receipt(Ed25519Signer(priv), seq=2, payload_hash="deadbeef")
    assert verify_receipt(r, "0ther", Ed25519Verifier(pub)) is False


def test_receipt_signed_by_wrong_key_is_rejected():
    priv, _ = _keypair()
    _, other_pub = _keypair()
    r = _issue_receipt(Ed25519Signer(priv), seq=2, payload_hash="deadbeef")
    assert verify_receipt(r, "deadbeef", Ed25519Verifier(other_pub)) is False


def test_tampered_receipt_field_is_rejected():
    priv, pub = _keypair()
    r = _issue_receipt(Ed25519Signer(priv), seq=2, payload_hash="deadbeef")
    # Attacker bumps received_at_ns after signing → signature no longer matches.
    tampered = Receipt(seq=r.seq, payload_hash=r.payload_hash,
                       received_at_ns=r.received_at_ns + 5,
                       signature=r.signature)
    assert verify_receipt(tampered, "deadbeef", Ed25519Verifier(pub)) is False


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def test_receipt_without_inclusion_is_attributable_omission():
    # Operator signed a receipt for seq=2 but never logged its inspection.
    assert attributable_omissions([0, 1, 2], observed_seqs=[0, 1, 3]) == [2]


def test_gap_without_receipt_is_not_attributable():
    # seq=2 has no receipt → could be a network failure → NOT attributable.
    assert attributable_omissions([0, 1, 3], observed_seqs=[0, 1, 3]) == []


def test_all_receipted_and_observed_means_no_omission():
    assert attributable_omissions([0, 1, 2, 3], observed_seqs=[0, 1, 2, 3]) == []


def test_multiple_attributable_omissions_sorted():
    assert attributable_omissions([0, 1, 2, 4, 5],
                                  observed_seqs=[0, 3]) == [1, 2, 4, 5]


# ---------------------------------------------------------------------------
# Idempotency: resending (seq, payload_hash) must not create a second leaf
# ---------------------------------------------------------------------------


def test_idempotent_resend_keeps_single_entry():
    """Model an operator that dedups by (seq, payload_hash) on retry."""
    committed: dict[int, str] = {}

    def commit(seq: int, payload_hash: str) -> int:
        # Returns the index; idempotent on (seq, payload_hash).
        if seq in committed:
            assert committed[seq] == payload_hash, "seq reused for different payload"
            return seq  # existing index, no new leaf
        committed[seq] = payload_hash
        return seq

    commit(0, "h0")
    commit(1, "h1")
    first = commit(1, "h1")  # retry after a network failure
    second = commit(1, "h1")
    assert first == second == 1
    assert len(committed) == 2  # only seq 0 and 1, no duplicate leaf


def test_seq_reuse_for_different_payload_is_detected():
    committed: dict[int, str] = {0: "h0"}

    def commit(seq: int, payload_hash: str) -> int:
        if seq in committed and committed[seq] != payload_hash:
            raise ValueError("seq reused for different payload")
        committed[seq] = payload_hash
        return seq

    with pytest.raises(ValueError, match="reused"):
        commit(0, "different-hash")
