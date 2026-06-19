"""End-to-end del lado servidor del gossip: HttpWitnessTransport → WitnessServer.

Cierra el hueco real (el servidor receptor). Usa un ThreadingHTTPServer en
localhost dentro del propio test (hilo daemon + teardown); no es subproceso ni GUI.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier
from atlas.transparency.gossip import (
    GossipMessage,
    HttpWitnessTransport,
    WitnessNetwork,
)
from atlas.transparency.log import SignedTreeHead
from atlas.transparency.witness import Witness
from atlas.transparency.witness_server import WitnessServer


def _keypair() -> tuple[Ed25519Signer, Ed25519Verifier]:
    k = Ed25519PrivateKey.generate()
    return Ed25519Signer(k.private_bytes_raw()), Ed25519Verifier(k.public_key().public_bytes_raw())


def _signed_sth(log_signer: Ed25519Signer, *, tree_size: int, root: bytes, ts: int = 1) -> SignedTreeHead:
    draft = SignedTreeHead(tree_size=tree_size, root_hash=root, timestamp=ts, signature="", algo="ed25519")
    sig = log_signer.sign(draft._payload())
    return SignedTreeHead(tree_size=tree_size, root_hash=root, timestamp=ts, signature=sig, algo="ed25519")


def _msg(sth: SignedTreeHead, wid: str = "w1") -> bytes:
    return GossipMessage(witness_id=wid, sth=sth, received_at_ns=123).to_bytes()


@pytest.fixture()
def setup():
    log_signer, log_verifier = _keypair()          # firma los STH (operador/log)
    wit_signer, wit_verifier = _keypair()           # counter-firma del testigo
    witness = Witness(log_verifier)                 # acepta STH firmados por la log
    server = WitnessServer(witness, wit_signer)
    server.start()
    try:
        yield log_signer, wit_verifier, server
    finally:
        server.stop()


def test_counter_sign_roundtrip(setup):
    """STH válido → el servidor counter-firma y la firma verifica."""
    log_signer, wit_verifier, server = setup
    sth = _signed_sth(log_signer, tree_size=5, root=b"\x11" * 32)
    body = _msg(sth)
    transport = HttpWitnessTransport({"w1": f"{server.url}/"})
    counter_sig = transport.post("w1", body)
    assert counter_sig is not None and counter_sig != ""
    # La counter-signature verifica sobre el CUERPO del gossip (contrato de
    # WitnessNetwork.broadcast), no sobre sth._payload().
    assert wit_verifier.verify(body, counter_sig)


def test_split_view_returns_409(setup):
    """Dos STH con el mismo tree_size y root distinto → el segundo da 409."""
    log_signer, _wit_verifier, server = setup
    sth_a = _signed_sth(log_signer, tree_size=7, root=b"\xaa" * 32)
    sth_b = _signed_sth(log_signer, tree_size=7, root=b"\xbb" * 32)  # conflicto
    url = f"{server.url}/"

    # Primer STH: aceptado (200).
    req_a = urllib.request.Request(url, data=_msg(sth_a), method="POST")
    with urllib.request.urlopen(req_a, timeout=5) as resp:
        assert resp.status == 200

    # Segundo STH conflictivo: split-view → 409.
    req_b = urllib.request.Request(url, data=_msg(sth_b), method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req_b, timeout=5)
    assert exc.value.code == 409

    # Vía el transporte tolerante a fallos: el conflicto se traduce en None.
    transport = HttpWitnessTransport({"w1": url})
    assert transport.post("w1", _msg(sth_b)) is None


def test_invalid_signature_returns_400(setup):
    """STH con firma inválida → 400 (el testigo no lo acepta)."""
    _log_signer, _wit_verifier, server = setup
    bad = SignedTreeHead(tree_size=3, root_hash=b"\x00" * 32, timestamp=1,
                         signature="not-a-valid-signature", algo="ed25519")
    req = urllib.request.Request(f"{server.url}/", data=_msg(bad), method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400


def test_malformed_body_returns_400(setup):
    """Cuerpo no parseable → 400, sin caer el servidor."""
    _log_signer, _wit_verifier, server = setup
    req = urllib.request.Request(f"{server.url}/", data=b"{not json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400


def test_quorum_over_http_two_servers():
    """Integración de red: WitnessNetwork difunde por HTTP a 2 WitnessServer
    reales → ambos counter-firman → has_quorum(min_witnesses=2) True.

    Valida que el WitnessServer compone con WitnessNetwork.broadcast (la
    counter-firma sobre el cuerpo del gossip verifica en la red).
    """
    log_signer, log_verifier = _keypair()
    s1, v1 = _keypair()
    s2, v2 = _keypair()
    srv1 = WitnessServer(Witness(log_verifier), s1)
    srv2 = WitnessServer(Witness(log_verifier), s2)
    srv1.start()
    srv2.start()
    try:
        http = HttpWitnessTransport({"w1": f"{srv1.url}/", "w2": f"{srv2.url}/"})
        net = WitnessNetwork(
            log_verifier,
            counter_transport=http.post,
            witness_verifiers={"w1": v1, "w2": v2},
        )
        net.register("w1", Witness(log_verifier))
        net.register("w2", Witness(log_verifier))

        sth = _signed_sth(log_signer, tree_size=9, root=b"\x22" * 32)
        net.broadcast(GossipMessage(witness_id="op", sth=sth, received_at_ns=1))

        assert net.counter_signature_coverage(9) == 2
        assert net.has_quorum(9, min_witnesses=2) is True
    finally:
        srv1.stop()
        srv2.stop()
