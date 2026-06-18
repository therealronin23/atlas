"""Tests para ADR-053 T5 — ClientCosigner + detect_omission."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from atlas.security.authorization import HMACSigner, HMACVerifier
from atlas.transparency.client_cosign import (
    ClientCosigner,
    CosignedRequest,
    detect_omission,
    verify_cosigned_request,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

KEY_A = b"key-alice-32-bytes-padding-xxxxx"
KEY_B = b"key-bob-other-32-bytes-padding!!"


@pytest.fixture()
def signer_a() -> HMACSigner:
    return HMACSigner(KEY_A)


@pytest.fixture()
def verifier_a() -> HMACVerifier:
    return HMACVerifier(KEY_A)


@pytest.fixture()
def verifier_b() -> HMACVerifier:
    """Verifier con clave distinta — no debe verificar firmas de signer_a."""
    return HMACVerifier(KEY_B)


# ---------------------------------------------------------------------------
# T5.1 — Secuencia monótona estrictamente creciente
# ---------------------------------------------------------------------------

class TestMonotonicSequence:
    def test_first_seq_is_zero(self, signer_a: HMACSigner) -> None:
        cosigner = ClientCosigner(signer_a)
        req = cosigner.sign_request(b"hello")
        assert req.seq == 0

    def test_seq_increments(self, signer_a: HMACSigner) -> None:
        cosigner = ClientCosigner(signer_a)
        seqs = [cosigner.sign_request(b"x").seq for _ in range(5)]
        assert seqs == list(range(5))

    def test_last_seq_tracks(self, signer_a: HMACSigner) -> None:
        cosigner = ClientCosigner(signer_a)
        for _ in range(3):
            cosigner.sign_request(b"payload")
        assert cosigner.last_seq == 2

    def test_custom_start_seq(self, signer_a: HMACSigner) -> None:
        cosigner = ClientCosigner(signer_a, start_seq=10)
        req = cosigner.sign_request(b"x")
        assert req.seq == 10
        assert cosigner.sign_request(b"y").seq == 11


# ---------------------------------------------------------------------------
# T5.2 — Verificación de co-firma
# ---------------------------------------------------------------------------

class TestCosignVerification:
    def test_valid_signature(
        self, signer_a: HMACSigner, verifier_a: HMACVerifier
    ) -> None:
        cosigner = ClientCosigner(signer_a)
        payload = b"important request"
        req = cosigner.sign_request(payload)
        assert verify_cosigned_request(req, payload, verifier_a) is True

    def test_wrong_key_rejected(
        self, signer_a: HMACSigner, verifier_b: HMACVerifier
    ) -> None:
        cosigner = ClientCosigner(signer_a)
        payload = b"request"
        req = cosigner.sign_request(payload)
        assert verify_cosigned_request(req, payload, verifier_b) is False

    def test_altered_payload_rejected(
        self, signer_a: HMACSigner, verifier_a: HMACVerifier
    ) -> None:
        cosigner = ClientCosigner(signer_a)
        payload = b"original"
        req = cosigner.sign_request(payload)
        # Payload modificado → hash no coincide
        assert verify_cosigned_request(req, b"tampered", verifier_a) is False

    def test_tampered_payload_hash_rejected(
        self, signer_a: HMACSigner, verifier_a: HMACVerifier
    ) -> None:
        cosigner = ClientCosigner(signer_a)
        payload = b"data"
        req = cosigner.sign_request(payload)
        # Sustituir el hash por uno falso manteniendo la firma intacta
        bad_req = CosignedRequest(
            seq=req.seq,
            payload_hash="a" * 64,
            signature=req.signature,
        )
        assert verify_cosigned_request(bad_req, payload, verifier_a) is False

    def test_tampered_signature_rejected(
        self, signer_a: HMACSigner, verifier_a: HMACVerifier
    ) -> None:
        cosigner = ClientCosigner(signer_a)
        payload = b"data"
        req = cosigner.sign_request(payload)
        bad_req = CosignedRequest(
            seq=req.seq,
            payload_hash=req.payload_hash,
            signature="00" * 32,  # firma incorrecta (64 hex chars)
        )
        assert verify_cosigned_request(bad_req, payload, verifier_a) is False


# ---------------------------------------------------------------------------
# T5.3 — detect_omission
# ---------------------------------------------------------------------------

class TestDetectOmission:
    def test_no_gaps_returns_empty(self) -> None:
        # Todos los seqs registrados
        assert detect_omission([0, 1, 2, 3], last_emitted=3) == []

    def test_intermediate_gap(self) -> None:
        # seq 1 y 2 omitidos
        assert detect_omission([0, 3], last_emitted=3) == [1, 2]

    def test_final_gap(self) -> None:
        # seq 3 y 4 (finales) omitidos
        assert detect_omission([0, 1, 2], last_emitted=4) == [3, 4]

    def test_mixed_gaps(self) -> None:
        # Huecos intermedios y finales
        result = detect_omission([0, 2, 4], last_emitted=6)
        assert result == [1, 3, 5, 6]

    def test_all_omitted(self) -> None:
        assert detect_omission([], last_emitted=2) == [0, 1, 2]

    def test_single_seq_present(self) -> None:
        assert detect_omission([0], last_emitted=0) == []

    def test_last_emitted_negative_returns_empty(self) -> None:
        # No se emitió ningún request
        assert detect_omission([], last_emitted=-1) == []

    def test_duplicate_observed_seqs(self) -> None:
        # Duplicados en observed no causan falsos positivos
        assert detect_omission([0, 0, 1, 1, 2], last_emitted=2) == []

    def test_operator_omits_inspection_detectable(
        self, signer_a: HMACSigner, verifier_a: HMACVerifier
    ) -> None:
        """El operador inspecciona 3 requests pero solo registra 2.

        El cliente detecta la laguna: el seq no registrado aparece como hueco.
        """
        cosigner = ClientCosigner(signer_a)
        payloads = [b"req0", b"req1", b"req2"]
        for p in payloads:
            cosigner.sign_request(p)

        # Operador registra seq 0 y 2 pero NO seq 1
        observed = [0, 2]
        gaps = detect_omission(observed, last_emitted=cosigner.last_seq)
        assert gaps == [1]
