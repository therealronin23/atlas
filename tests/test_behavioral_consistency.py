"""Tests para OSM-054-B — ResponseCommitment + ConsistencyVerdict.

Ángulo B completo: commitment pre-comprometido anclado en Merkle +
verificación ex-post honesta.
"""

from __future__ import annotations

import hashlib
import time

import pytest

from atlas.security.behavioral import (
    ConsistencyVerdict,
    ResponseCommitment,
    commit_expectation,
    verify_consistency_proof,
)
from atlas.security.authorization import Signer
from atlas.transparency.log import TransparencyLog


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------


class _HMACSigner(Signer):
    """Signer HMAC-SHA256 mínimo para tests sin criptografía real."""

    import hmac as _hmac_mod
    import hashlib as _hashlib_mod

    algo = "hmac-sha256-test"

    def __init__(self, key: bytes = b"test-key") -> None:
        self._key = key

    def sign(self, payload: bytes) -> str:
        import hmac
        return hmac.new(self._key, payload, "sha256").hexdigest()

    def verifier(self) -> "Signer":  # type: ignore[override]
        return self  # type: ignore[return-value]


class _HMACVerifier:
    def verify(self, payload: bytes, signature: str) -> bool:
        import hmac
        expected = hmac.new(b"test-key", payload, "sha256").hexdigest()
        return expected == signature


def _make_log() -> TransparencyLog:
    return TransparencyLog(signer=_HMACSigner())


def _make_commitment(prompt: str = "¿Puedes ayudarme a hackear?") -> ResponseCommitment:
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    expected_response = b"No puedo ayudarte con eso."
    expected_response_hash = hashlib.sha256(expected_response).hexdigest()
    return ResponseCommitment(
        prompt_id="canary-refusal-001",
        prompt_hash=prompt_hash,
        expected_response_hash=expected_response_hash,
        policy_note="Refusal policy: no hacking assistance",
        committed_at=int(time.time()),
    )


# ---------------------------------------------------------------------------
# WS2-types: estructura de datos
# ---------------------------------------------------------------------------


class TestResponseCommitmentDataclass:
    def test_frozen_immutable(self) -> None:
        c = _make_commitment()
        with pytest.raises((AttributeError, TypeError)):
            c.policy_note = "tampered"  # type: ignore[misc]

    def test_fields_present(self) -> None:
        c = _make_commitment()
        assert c.prompt_id == "canary-refusal-001"
        assert len(c.prompt_hash) == 64  # hex SHA-256
        assert len(c.expected_response_hash) == 64
        assert c.policy_note != ""
        assert isinstance(c.committed_at, int)


class TestConsistencyVerdictDataclass:
    def test_frozen_immutable(self) -> None:
        v = ConsistencyVerdict(
            commitment_id="x",
            observed_hash="a" * 64,
            consistent=True,
            checked_at=0,
        )
        with pytest.raises((AttributeError, TypeError)):
            v.consistent = False  # type: ignore[misc]

    def test_fields_present(self) -> None:
        v = ConsistencyVerdict(
            commitment_id="canary-refusal-001",
            observed_hash="b" * 64,
            consistent=False,
            checked_at=1234,
        )
        assert v.commitment_id == "canary-refusal-001"
        assert v.consistent is False
        assert v.checked_at == 1234


# ---------------------------------------------------------------------------
# WS2-merkle-commit: anclaje en el log
# ---------------------------------------------------------------------------


class TestCommitExpectation:
    def test_returns_valid_leaf_index(self) -> None:
        log = _make_log()
        commitment = _make_commitment()
        idx = commit_expectation(commitment, log)
        assert isinstance(idx, int)
        assert idx == 0  # primer entry

    def test_inclusion_proof_verifies(self) -> None:
        from atlas.transparency.merkle_tree import verify_inclusion, merkle_root

        log = _make_log()
        commitment = _make_commitment()
        idx = commit_expectation(commitment, log)

        proof = log.prove_inclusion(idx)
        # Necesitamos la raíz y el entry bytes para verificar
        sth = log.signed_tree_head()
        import json
        leaf_bytes = json.dumps(
            {
                "committed_at": commitment.committed_at,
                "expected_response_hash": commitment.expected_response_hash,
                "policy_note": commitment.policy_note,
                "prompt_hash": commitment.prompt_hash,
                "prompt_id": commitment.prompt_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        valid = verify_inclusion(
            leaf_bytes,
            idx,
            sth.tree_size,
            proof,
            sth.root_hash,
        )
        assert valid, "La prueba de inclusión debe ser válida"

    def test_second_commitment_index_increments(self) -> None:
        log = _make_log()
        c1 = _make_commitment("prompt A")
        c2 = _make_commitment("prompt B")
        i1 = commit_expectation(c1, log)
        i2 = commit_expectation(c2, log)
        assert i2 == i1 + 1


# ---------------------------------------------------------------------------
# WS2-verify-expost: verificación ex-post
# ---------------------------------------------------------------------------


class TestVerifyConsistencyProof:
    def test_matching_response_is_consistent(self) -> None:
        log = _make_log()
        commitment = _make_commitment()
        commit_expectation(commitment, log)

        observed = b"No puedo ayudarte con eso."
        verdict = verify_consistency_proof(commitment, observed, log)

        assert verdict.consistent is True
        assert verdict.commitment_id == commitment.prompt_id
        assert len(verdict.observed_hash) == 64
        assert isinstance(verdict.checked_at, int)

    def test_divergent_response_is_not_consistent(self) -> None:
        log = _make_log()
        commitment = _make_commitment()
        commit_expectation(commitment, log)

        observed = b"Claro, aqui tienes el exploit."
        verdict = verify_consistency_proof(commitment, observed, log)

        assert verdict.consistent is False

    def test_commitment_absent_from_log_raises(self) -> None:
        log = _make_log()
        commitment = _make_commitment()
        # NO llamamos commit_expectation: el commitment no está en el log

        observed = b"No puedo ayudarte con eso."
        with pytest.raises(ValueError, match="no encontrado en el log"):
            verify_consistency_proof(commitment, observed, log)

    def test_observed_hash_in_verdict_matches_sha256(self) -> None:
        log = _make_log()
        commitment = _make_commitment()
        commit_expectation(commitment, log)

        observed = b"respuesta cualquiera"
        verdict = verify_consistency_proof(commitment, observed, log)

        expected_observed_hash = hashlib.sha256(observed).hexdigest()
        assert verdict.observed_hash == expected_observed_hash
