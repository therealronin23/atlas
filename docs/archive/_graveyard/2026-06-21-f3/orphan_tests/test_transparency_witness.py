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


# ---------------------------------------------------------------------------
# HttpWitnessTransport — mocked urllib.request.urlopen (no red real)
# ---------------------------------------------------------------------------


import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier
from atlas.transparency.gossip import HttpWitnessTransport, WitnessNetwork, GossipMessage


ENDPOINTS = {"w1": "http://witness1.local/sth", "w2": "http://witness2.local/sth"}
_PAYLOAD = b"test-payload"


def _make_resp(body: bytes) -> MagicMock:
    """Crea un context-manager mock que simula la respuesta de urlopen."""
    resp = MagicMock()
    resp.read.return_value = body
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestHttpTransport:
    def test_http_transport_post_success(self) -> None:
        transport = HttpWitnessTransport(ENDPOINTS)
        with patch("urllib.request.urlopen", return_value=_make_resp(b"sig_abc")) as mock_open:
            result = transport.post("w1", _PAYLOAD)
        assert result == "sig_abc"
        mock_open.assert_called_once()

    def test_http_transport_retry_on_timeout(self) -> None:
        transport = HttpWitnessTransport(ENDPOINTS)
        success_cm = _make_resp(b"sig_ok")
        with patch(
            "urllib.request.urlopen",
            side_effect=[urllib.error.URLError("timeout"), success_cm],
        ) as mock_open:
            result = transport.post("w1", _PAYLOAD)
        assert result == "sig_ok"
        assert mock_open.call_count == 2

    def test_http_transport_both_fail_returns_none(self, caplog) -> None:
        transport = HttpWitnessTransport(ENDPOINTS)
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                urllib.error.URLError("timeout"),
                urllib.error.URLError("timeout"),
            ],
        ):
            result = transport.post("w1", _PAYLOAD)
        assert result is None
        assert any("retry failed" in r.message for r in caplog.records)

    def test_http_transport_unknown_witness_returns_none(self) -> None:
        transport = HttpWitnessTransport(ENDPOINTS)
        with patch("urllib.request.urlopen") as mock_open:
            result = transport.post("unknown_witness", _PAYLOAD)
        assert result is None
        mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# WitnessNetwork quorum via counter_transport mock
# ---------------------------------------------------------------------------


class TestWitnessNetworkQuorum:
    def _make_sth(self, signer: HMACSigner, tree_size: int = 3) -> SignedTreeHead:
        root = b"\xab" * 32
        draft = SignedTreeHead(
            tree_size=tree_size,
            root_hash=root,
            timestamp=1_000_000,
            signature="",
            algo=signer.algo,
        )
        sig = signer.sign(draft._payload())
        return SignedTreeHead(
            tree_size=tree_size,
            root_hash=root,
            timestamp=1_000_000,
            signature=sig,
            algo=signer.algo,
        )

    def test_witness_network_quorum_with_two_witnesses(
        self, signer: HMACSigner, verifier: HMACVerifier
    ) -> None:
        """Quórum alcanzado cuando dos witnesses firman con Ed25519 real."""
        w1_signer, w1_verifier = _make_ed25519()
        w2_signer, w2_verifier = _make_ed25519()

        def counter_transport(witness_id: str, payload: bytes) -> str:
            return w1_signer.sign(payload) if witness_id == "w1" else w2_signer.sign(payload)

        net = WitnessNetwork(
            sig_verifier=verifier,
            counter_transport=counter_transport,
            witness_verifiers={"w1": w1_verifier, "w2": w2_verifier},
        )
        w1 = Witness(sig_verifier=verifier)
        w2 = Witness(sig_verifier=verifier)
        net.register("w1", w1)
        net.register("w2", w2)

        sth = self._make_sth(signer, tree_size=3)
        msg = GossipMessage(witness_id="w1", sth=sth, received_at_ns=0)
        net.broadcast(msg)

        assert net.counter_signature_coverage(3) == 2
        assert net.has_quorum(3) is True

    def test_witness_network_none_witness_does_not_count(
        self, signer: HMACSigner, verifier: HMACVerifier
    ) -> None:
        counter_transport = MagicMock(return_value=None)
        net = WitnessNetwork(
            sig_verifier=verifier,
            counter_transport=counter_transport,
        )
        w1 = Witness(sig_verifier=verifier)
        w2 = Witness(sig_verifier=verifier)
        net.register("w1", w1)
        net.register("w2", w2)

        sth = self._make_sth(signer, tree_size=5)
        msg = GossipMessage(witness_id="w1", sth=sth, received_at_ns=0)
        net.broadcast(msg)

        assert net.has_quorum(5) is False


# ---------------------------------------------------------------------------
# WitnessNetwork — verificación criptográfica de counter-signatures (Ed25519)
# ---------------------------------------------------------------------------


def _make_ed25519() -> tuple[Ed25519Signer, Ed25519Verifier]:
    """Genera un par Ed25519 efímero para tests."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes_raw()
    pub_bytes = priv.public_key().public_bytes_raw()
    return Ed25519Signer(priv_bytes), Ed25519Verifier(pub_bytes)


class TestWitnessNetworkCounterSigVerification:
    """Verifica que WitnessNetwork valide criptográficamente las counter-sigs."""

    def _make_hmac_sth(
        self, signer: HMACSigner, tree_size: int = 3
    ) -> SignedTreeHead:
        root = b"\xab" * 32
        draft = SignedTreeHead(
            tree_size=tree_size,
            root_hash=root,
            timestamp=1_000_000,
            signature="",
            algo=signer.algo,
        )
        sig = signer.sign(draft._payload())
        return SignedTreeHead(
            tree_size=tree_size,
            root_hash=root,
            timestamp=1_000_000,
            signature=sig,
            algo=signer.algo,
        )

    def test_counter_signature_garbage_does_not_count(
        self, signer: HMACSigner, verifier: HMACVerifier
    ) -> None:
        """Un transport comprometido que devuelve basura no alcanza quórum."""
        _, w1_verifier = _make_ed25519()
        _, w2_verifier = _make_ed25519()

        # El transport devuelve una string que no es hex válido.
        counter_transport = MagicMock(return_value="notavalidhex")
        net = WitnessNetwork(
            sig_verifier=verifier,
            counter_transport=counter_transport,
            witness_verifiers={"w1": w1_verifier, "w2": w2_verifier},
        )
        w1 = Witness(sig_verifier=verifier)
        w2 = Witness(sig_verifier=verifier)
        net.register("w1", w1)
        net.register("w2", w2)

        sth = self._make_hmac_sth(signer, tree_size=7)
        msg = GossipMessage(witness_id="w1", sth=sth, received_at_ns=0)
        net.broadcast(msg)

        assert net.has_quorum(7) is False

    def test_counter_signature_valid_reaches_quorum(
        self, signer: HMACSigner, verifier: HMACVerifier
    ) -> None:
        """Dos witnesses que firman de verdad con Ed25519 alcanzan quórum."""
        w1_signer, w1_verifier = _make_ed25519()
        w2_signer, w2_verifier = _make_ed25519()

        sth = self._make_hmac_sth(signer, tree_size=9)
        # El transport simula cada testigo firmando el payload con su clave real.
        # El payload que llega al transport es el GossipMessage serializado.
        def counter_transport(witness_id: str, payload: bytes) -> str:
            if witness_id == "w1":
                return w1_signer.sign(payload)
            if witness_id == "w2":
                return w2_signer.sign(payload)
            return "bad"

        net = WitnessNetwork(
            sig_verifier=verifier,
            counter_transport=counter_transport,
            witness_verifiers={"w1": w1_verifier, "w2": w2_verifier},
        )
        w1 = Witness(sig_verifier=verifier)
        w2 = Witness(sig_verifier=verifier)
        net.register("w1", w1)
        net.register("w2", w2)

        msg = GossipMessage(witness_id="w1", sth=sth, received_at_ns=0)
        net.broadcast(msg)

        assert net.counter_signature_coverage(9) == 2
        assert net.has_quorum(9) is True

    def test_witness_network_quorum_without_verifiers_does_not_count(
        self, signer: HMACSigner, verifier: HMACVerifier
    ) -> None:
        """Sin witness_verifiers, ninguna counter-sig se cuenta (safe default)."""
        counter_transport = MagicMock(return_value="any_string")
        net = WitnessNetwork(
            sig_verifier=verifier,
            counter_transport=counter_transport,
            # witness_verifiers=None  ← omitido intencionalmente
        )
        w1 = Witness(sig_verifier=verifier)
        w2 = Witness(sig_verifier=verifier)
        net.register("w1", w1)
        net.register("w2", w2)

        sth = self._make_hmac_sth(signer, tree_size=11)
        msg = GossipMessage(witness_id="w1", sth=sth, received_at_ns=0)
        net.broadcast(msg)

        assert net.has_quorum(11) is False
