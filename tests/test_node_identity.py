"""Tests para t6-node-identity-module — NodeIdentity standalone.

Cubre round-trip firma→verificación de heartbeats y rechazo ante firma/
payload alterados. Módulo puro sin transporte remoto (ver docstring de
node_identity.py) — estos tests no tocan red ni control-plane.
"""

from __future__ import annotations

import json

import pytest

from atlas.security.node_identity import (
    NodeIdentity,
    NodeIdentityDocument,
    SignedHeartbeat,
    verify_heartbeat,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def node() -> NodeIdentity:
    return NodeIdentity.generate(node_id="node-alpha", metadata={"role": "test"})


@pytest.fixture()
def other_node() -> NodeIdentity:
    return NodeIdentity.generate(node_id="node-beta")


# ---------------------------------------------------------------------------
# Generación de keypair + documento de identidad
# ---------------------------------------------------------------------------

class TestNodeIdentityGeneration:
    def test_generate_produces_distinct_keys(self) -> None:
        a = NodeIdentity.generate(node_id="a")
        b = NodeIdentity.generate(node_id="b")
        assert a.public_key_hex != b.public_key_hex

    def test_generate_without_node_id_assigns_uuid(self) -> None:
        n = NodeIdentity.generate()
        assert n.node_id  # non-empty
        assert NodeIdentity.generate().node_id != n.node_id

    def test_identity_document_has_public_key_and_metadata(
        self, node: NodeIdentity
    ) -> None:
        doc = node.identity_document()
        assert isinstance(doc, NodeIdentityDocument)
        assert doc.node_id == "node-alpha"
        assert doc.public_key_hex == node.public_key_hex
        assert doc.algo == "ed25519"
        assert doc.metadata == {"role": "test"}

    def test_identity_document_json_round_trip(self, node: NodeIdentity) -> None:
        doc = node.identity_document()
        raw = doc.to_json()
        # documento es JSON válido y serializable de forma determinista
        assert json.loads(raw)["public_key_hex"] == node.public_key_hex
        restored = NodeIdentityDocument.from_json(raw)
        assert restored == doc


# ---------------------------------------------------------------------------
# Round-trip firma -> verificación de heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeatRoundTrip:
    def test_sign_and_verify_succeeds(self, node: NodeIdentity) -> None:
        payload = b"heartbeat-payload-1"
        hb = node.sign_heartbeat(payload, seq=0)
        assert isinstance(hb, SignedHeartbeat)
        assert verify_heartbeat(hb, payload, node.public_key_hex) is True

    def test_verify_using_only_public_key_no_private_material(
        self, node: NodeIdentity
    ) -> None:
        """El verificador solo necesita el hex de clave pública del documento
        de identidad — no el objeto NodeIdentity ni la clave privada."""
        payload = b"receipt-payload"
        hb = node.sign_heartbeat(payload, seq=3)
        doc = node.identity_document()
        assert verify_heartbeat(hb, payload, doc.public_key_hex) is True

    def test_heartbeat_json_round_trip(self, node: NodeIdentity) -> None:
        hb = node.sign_heartbeat(b"payload", seq=1)
        restored = SignedHeartbeat.from_json(hb.to_json())
        assert restored == hb
        assert verify_heartbeat(restored, b"payload", node.public_key_hex) is True

    def test_seq_and_node_id_are_bound_in_heartbeat(self, node: NodeIdentity) -> None:
        hb = node.sign_heartbeat(b"payload", seq=7)
        assert hb.seq == 7
        assert hb.node_id == "node-alpha"


# ---------------------------------------------------------------------------
# Rechazo ante firma / payload alterados
# ---------------------------------------------------------------------------

class TestHeartbeatRejection:
    def test_altered_signature_is_rejected(self, node: NodeIdentity) -> None:
        payload = b"heartbeat-payload"
        hb = node.sign_heartbeat(payload, seq=0)
        tampered_sig = ("0" if hb.signature[0] != "0" else "1") + hb.signature[1:]
        tampered = SignedHeartbeat(
            node_id=hb.node_id,
            seq=hb.seq,
            timestamp_ns=hb.timestamp_ns,
            payload_hash=hb.payload_hash,
            signature=tampered_sig,
        )
        assert verify_heartbeat(tampered, payload, node.public_key_hex) is False

    def test_altered_payload_is_rejected(self, node: NodeIdentity) -> None:
        hb = node.sign_heartbeat(b"original-payload", seq=0)
        assert verify_heartbeat(hb, b"tampered-payload", node.public_key_hex) is False

    def test_altered_seq_is_rejected(self, node: NodeIdentity) -> None:
        payload = b"payload"
        hb = node.sign_heartbeat(payload, seq=0)
        tampered = SignedHeartbeat(
            node_id=hb.node_id,
            seq=99,
            timestamp_ns=hb.timestamp_ns,
            payload_hash=hb.payload_hash,
            signature=hb.signature,
        )
        assert verify_heartbeat(tampered, payload, node.public_key_hex) is False

    def test_wrong_public_key_is_rejected(
        self, node: NodeIdentity, other_node: NodeIdentity
    ) -> None:
        payload = b"payload"
        hb = node.sign_heartbeat(payload, seq=0)
        assert verify_heartbeat(hb, payload, other_node.public_key_hex) is False

    def test_malformed_signature_hex_does_not_raise(self, node: NodeIdentity) -> None:
        payload = b"payload"
        hb = node.sign_heartbeat(payload, seq=0)
        tampered = SignedHeartbeat(
            node_id=hb.node_id,
            seq=hb.seq,
            timestamp_ns=hb.timestamp_ns,
            payload_hash=hb.payload_hash,
            signature="not-valid-hex-zz",
        )
        assert verify_heartbeat(tampered, payload, node.public_key_hex) is False
