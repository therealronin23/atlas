"""Tests para ADR-053 Gossip protocol — GossipMessage y WitnessNetwork."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call

import pytest

from atlas.transparency.gossip import GossipMessage, WitnessNetwork
from atlas.transparency.log import SignedTreeHead
from atlas.transparency.witness import InvalidSignatureError, Witness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sth(tree_size: int = 10, root_hash: bytes = b"abc123") -> SignedTreeHead:
    return SignedTreeHead(
        tree_size=tree_size,
        root_hash=root_hash,
        timestamp=1000,
        signature="sig",
        algo="ed25519",
    )


def _make_msg(
    witness_id: str = "w1",
    tree_size: int = 10,
    root_hash: bytes = b"abc123",
) -> GossipMessage:
    return GossipMessage(
        witness_id=witness_id,
        sth=_make_sth(tree_size, root_hash),
        received_at_ns=2000,
    )


def _accepting_verifier() -> MagicMock:
    """SigVerifier que siempre devuelve True."""
    v = MagicMock()
    v.verify.return_value = True
    return v


def _rejecting_verifier() -> MagicMock:
    """SigVerifier que siempre devuelve False."""
    v = MagicMock()
    v.verify.return_value = False
    return v


# ---------------------------------------------------------------------------
# Tests originales (GossipMessage)
# ---------------------------------------------------------------------------


def test_gossip_message_frozen() -> None:
    """GossipMessage es frozen (dataclass inmutable)."""
    msg = _make_msg()
    try:
        msg.witness_id = "w2"  # type: ignore
        assert False, "debe ser frozen"
    except (AttributeError, TypeError):
        pass


def test_gossip_message_to_bytes_canonical() -> None:
    """to_bytes() produce JSON canónico con sort_keys=True."""
    sth = SignedTreeHead(
        tree_size=42,
        root_hash=b"\x00\x01\x02",
        timestamp=1234567890,
        signature="abcdef123456",
        algo="ed25519",
    )
    msg = GossipMessage(witness_id="witness-alpha", sth=sth, received_at_ns=9876543210)
    encoded = msg.to_bytes()
    assert isinstance(encoded, bytes)
    decoded = json.loads(encoded)
    assert list(decoded.keys()) == ["received_at_ns", "sth", "witness_id"]
    assert decoded["witness_id"] == "witness-alpha"
    assert decoded["received_at_ns"] == 9876543210
    assert decoded["sth"]["algo"] == "ed25519"
    assert decoded["sth"]["root_hash"] == "000102"
    assert b": " not in encoded
    assert b", " not in encoded


def test_gossip_message_roundtrip() -> None:
    """Serializar y deserializar preserva valores."""
    sth = _make_sth(100, b"sentinel")
    msg_orig = GossipMessage(witness_id="w-original", sth=sth, received_at_ns=6000)
    decoded = json.loads(msg_orig.to_bytes())
    msg_rebuilt = GossipMessage(
        witness_id=decoded["witness_id"],
        sth=SignedTreeHead(
            tree_size=decoded["sth"]["tree_size"],
            root_hash=bytes.fromhex(decoded["sth"]["root_hash"]),
            timestamp=decoded["sth"]["timestamp"],
            signature=decoded["sth"]["signature"],
            algo=decoded["sth"]["algo"],
        ),
        received_at_ns=decoded["received_at_ns"],
    )
    assert msg_rebuilt.witness_id == msg_orig.witness_id
    assert msg_rebuilt.sth.root_hash == msg_orig.sth.root_hash
    assert msg_rebuilt.received_at_ns == msg_orig.received_at_ns


def test_gossip_message_attributes() -> None:
    sth = _make_sth(7, b"hash")
    msg = GossipMessage(witness_id="witness-id", sth=sth, received_at_ns=888)
    assert msg.witness_id == "witness-id"
    assert msg.sth is sth
    assert msg.received_at_ns == 888


# ---------------------------------------------------------------------------
# Tests WitnessNetwork — register
# ---------------------------------------------------------------------------


def test_register_stores_witness() -> None:
    """register() almacena el testigo indexado por ID."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w = Witness(_accepting_verifier())
    net.register("w1", w)
    assert "w1" in net._witnesses
    assert net._witnesses["w1"] is w


def test_register_multiple_witnesses() -> None:
    """Se pueden registrar múltiples testigos con IDs distintos."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w1 = Witness(_accepting_verifier())
    w2 = Witness(_accepting_verifier())
    net.register("alpha", w1)
    net.register("beta", w2)
    assert len(net._witnesses) == 2


# ---------------------------------------------------------------------------
# Tests WitnessNetwork — broadcast
# ---------------------------------------------------------------------------


def test_broadcast_calls_transport_for_each_witness() -> None:
    """broadcast() llama al transport por cada testigo registrado."""
    calls_made: list[tuple[str, bytes]] = []

    def spy_transport(wid: str, data: bytes) -> None:
        calls_made.append((wid, data))

    net = WitnessNetwork(sig_verifier=_accepting_verifier(), transport=spy_transport)
    net.register("w1", Witness(_accepting_verifier()))
    net.register("w2", Witness(_accepting_verifier()))

    msg = _make_msg()
    net.broadcast(msg)

    assert len(calls_made) == 2
    wids = {c[0] for c in calls_made}
    assert wids == {"w1", "w2"}


def test_broadcast_calls_witness_observe() -> None:
    """broadcast() llama a observe() en cada Witness con el STH correcto."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w = MagicMock(spec=Witness)
    net.register("w1", w)
    net._seen_by["w1"] = set()

    msg = _make_msg()
    net.broadcast(msg)

    w.observe.assert_called_once_with(msg.sth)


def test_broadcast_transport_error_does_not_abort() -> None:
    """Error en transport de un witness no aborta la entrega a los demás."""
    delivered: list[str] = []

    def flaky_transport(wid: str, data: bytes) -> None:
        if wid == "bad":
            raise ConnectionError("timeout")
        delivered.append(wid)

    net = WitnessNetwork(sig_verifier=_accepting_verifier(), transport=flaky_transport)
    net.register("bad", Witness(_accepting_verifier()))
    net.register("good", Witness(_accepting_verifier()))

    msg = _make_msg()
    net.broadcast(msg)  # no debe lanzar

    assert "good" in delivered


def test_broadcast_invalid_signature_does_not_abort() -> None:
    """Firma inválida en un witness no aborta la red — log y continúa."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    bad_witness = Witness(_rejecting_verifier())   # siempre rechaza
    good_witness = Witness(_accepting_verifier())  # siempre acepta

    net.register("bad", bad_witness)
    net.register("good", good_witness)

    msg = _make_msg()
    net.broadcast(msg)  # no debe lanzar

    # El buen testigo vio el STH; el malo no (error capturado).
    assert msg.sth.tree_size in net._seen_by["good"]
    assert msg.sth.tree_size not in net._seen_by["bad"]


# ---------------------------------------------------------------------------
# Tests WitnessNetwork — check_quorum
# ---------------------------------------------------------------------------


def test_check_quorum_no_witnesses_returns_false() -> None:
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    assert net.check_quorum(10) is False


def test_check_quorum_all_witnesses_seen() -> None:
    """3/3 witnesses vieron el STH → quórum 2/3 alcanzado."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    for i in range(3):
        net.register(f"w{i}", Witness(_accepting_verifier()))

    msg = _make_msg(tree_size=42)
    net.broadcast(msg)

    assert net.check_quorum(42) is True


def test_check_quorum_exactly_two_thirds() -> None:
    """ceil(2/3*3) = 2 → necesita 2 de 3 para el quórum."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    # Dos testigos aceptan, uno rechaza.
    net.register("w0", Witness(_accepting_verifier()))
    net.register("w1", Witness(_accepting_verifier()))
    net.register("w2", Witness(_rejecting_verifier()))

    msg = _make_msg(tree_size=99)
    net.broadcast(msg)

    # 2 de 3 vieron → ceil(2/3*3) = 2 → quórum OK
    assert net.check_quorum(99) is True


def test_check_quorum_below_threshold() -> None:
    """Solo 1/3 witnesses vieron el STH → no alcanza quórum."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("w0", Witness(_accepting_verifier()))
    net.register("w1", Witness(_rejecting_verifier()))
    net.register("w2", Witness(_rejecting_verifier()))

    msg = _make_msg(tree_size=55)
    net.broadcast(msg)

    # 1 de 3 → ceil(2/3*3) = 2 → no alcanza
    assert net.check_quorum(55) is False


def test_check_quorum_unseen_tree_size_returns_false() -> None:
    """Quórum para un tree_size que nadie ha visto → False."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("w0", Witness(_accepting_verifier()))
    net.register("w1", Witness(_accepting_verifier()))
    net.register("w2", Witness(_accepting_verifier()))

    # Se hace broadcast de tree_size=10 pero se pregunta por 999.
    msg = _make_msg(tree_size=10)
    net.broadcast(msg)

    assert net.check_quorum(999) is False


# ---------------------------------------------------------------------------
# Tests adicionales — GossipMessage.to_bytes() canónico
# ---------------------------------------------------------------------------


def test_to_bytes_same_input_same_output() -> None:
    """to_bytes() es determinista: mismos datos → mismos bytes."""
    sth = _make_sth(5, b"deterministic")
    msg_a = GossipMessage(witness_id="wx", sth=sth, received_at_ns=111)
    msg_b = GossipMessage(witness_id="wx", sth=sth, received_at_ns=111)
    assert msg_a.to_bytes() == msg_b.to_bytes()


def test_to_bytes_different_witness_different_bytes() -> None:
    """witness_id distinto → bytes distintos."""
    sth = _make_sth(5, b"same")
    msg_a = GossipMessage(witness_id="w-alpha", sth=sth, received_at_ns=500)
    msg_b = GossipMessage(witness_id="w-beta",  sth=sth, received_at_ns=500)
    assert msg_a.to_bytes() != msg_b.to_bytes()


def test_to_bytes_different_timestamp_different_bytes() -> None:
    """received_at_ns distinto → bytes distintos."""
    sth = _make_sth(7, b"ts")
    msg_a = GossipMessage(witness_id="w1", sth=sth, received_at_ns=1000)
    msg_b = GossipMessage(witness_id="w1", sth=sth, received_at_ns=9999)
    assert msg_a.to_bytes() != msg_b.to_bytes()


def test_to_bytes_no_whitespace() -> None:
    """to_bytes() JSON compacto: sin espacios tras ':' ni ','."""
    msg = _make_msg()
    raw = msg.to_bytes()
    assert b": " not in raw
    assert b", " not in raw


# ---------------------------------------------------------------------------
# Tests adicionales — WitnessNetwork.register() duplicado
# ---------------------------------------------------------------------------


def test_register_duplicate_is_idempotent() -> None:
    """Registrar el mismo ID dos veces no duplica la entrada."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w = Witness(_accepting_verifier())
    net.register("dup", w)
    net.register("dup", w)
    assert len(net._witnesses) == 1
    assert net._witnesses["dup"] is w


def test_register_overwrites_with_new_witness() -> None:
    """Re-registrar misma ID con instancia distinta actualiza la referencia."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w1 = Witness(_accepting_verifier())
    w2 = Witness(_accepting_verifier())
    net.register("shared", w1)
    net.register("shared", w2)
    assert net._witnesses["shared"] is w2


# ---------------------------------------------------------------------------
# Tests adicionales — WitnessNetwork.broadcast() quórum 2/3 N=3
# ---------------------------------------------------------------------------


def test_broadcast_quorum_2_of_3_reached() -> None:
    """N=3 witnesses, 2 aceptan → quórum 2/3 alcanzado."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("w0", Witness(_accepting_verifier()))
    net.register("w1", Witness(_accepting_verifier()))
    net.register("w2", Witness(_rejecting_verifier()))

    msg = _make_msg(tree_size=77)
    net.broadcast(msg)
    assert net.check_quorum(77) is True


def test_broadcast_quorum_1_of_3_not_reached() -> None:
    """N=3 witnesses, solo 1 acepta → quórum NO alcanzado."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("w0", Witness(_accepting_verifier()))
    net.register("w1", Witness(_rejecting_verifier()))
    net.register("w2", Witness(_rejecting_verifier()))

    msg = _make_msg(tree_size=88)
    net.broadcast(msg)
    assert net.check_quorum(88) is False


def test_broadcast_invalid_sig_continues_to_next_witness() -> None:
    """Firma inválida en un witness no interrumpe entrega a los restantes."""
    seen_good: list[str] = []

    def spy(wid: str, data: bytes) -> None:
        seen_good.append(wid)

    net = WitnessNetwork(sig_verifier=_accepting_verifier(), transport=spy)
    net.register("bad", Witness(_rejecting_verifier()))
    net.register("good", Witness(_accepting_verifier()))

    msg = _make_msg(tree_size=33)
    net.broadcast(msg)  # no debe lanzar

    assert "good" in seen_good


# ---------------------------------------------------------------------------
# Tests adicionales — Transport callable inyectable
# ---------------------------------------------------------------------------


def test_transport_receives_correct_bytes() -> None:
    """El transport recibe exactamente msg.to_bytes() para cada witness."""
    received: dict[str, bytes] = {}

    def capturing_transport(wid: str, data: bytes) -> None:
        received[wid] = data

    net = WitnessNetwork(sig_verifier=_accepting_verifier(), transport=capturing_transport)
    net.register("t1", Witness(_accepting_verifier()))

    msg = _make_msg()
    net.broadcast(msg)

    assert received["t1"] == msg.to_bytes()


def test_transport_mock_object_called() -> None:
    """Transport como MagicMock — se puede inspeccionar la llamada."""
    mock_transport = MagicMock()
    net = WitnessNetwork(sig_verifier=_accepting_verifier(), transport=mock_transport)
    net.register("wm", Witness(_accepting_verifier()))

    msg = _make_msg(witness_id="wm", tree_size=20)
    net.broadcast(msg)

    mock_transport.assert_called_once_with("wm", msg.to_bytes())


# ---------------------------------------------------------------------------
# Tests adicionales — detect_split_view_across_witnesses
# ---------------------------------------------------------------------------


def test_detect_split_view_two_conflicting_witnesses() -> None:
    """Dos testigos con STH conflictivos → detect_split_view_across_witnesses() True."""
    from atlas.transparency.witness import InvalidSignatureError  # noqa: F401

    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w1 = Witness(_accepting_verifier())
    w2 = Witness(_accepting_verifier())
    net.register("wa", w1)
    net.register("wb", w2)

    # Mismo tree_size, diferentes root_hash → split-view.
    sth_a = _make_sth(tree_size=50, root_hash=b"aaaaaa")
    sth_b = _make_sth(tree_size=50, root_hash=b"bbbbbb")

    # Inyectar STHs directamente en _seen de cada witness para garantizar conflicto.
    w1._seen[50] = sth_a
    w2._seen[50] = sth_b

    assert net.detect_split_view_across_witnesses() is True


def test_detect_split_view_empty_network() -> None:
    """Red sin testigos → detect_split_view_across_witnesses() False (no crash)."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    assert net.detect_split_view_across_witnesses() is False


def test_detect_split_view_no_conflict() -> None:
    """Dos testigos con mismo root_hash → no hay split-view."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    w1 = Witness(_accepting_verifier())
    w2 = Witness(_accepting_verifier())
    net.register("p", w1)
    net.register("q", w2)

    sth = _make_sth(tree_size=60, root_hash=b"same__")
    w1._seen[60] = sth
    w2._seen[60] = sth

    assert net.detect_split_view_across_witnesses() is False


# ---------------------------------------------------------------------------
# Tests adicionales — check_quorum con diferentes N
# ---------------------------------------------------------------------------


def test_check_quorum_n1_single_witness_passes() -> None:
    """N=1: ceil(2/3*1)=1 → necesita 1 witness."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("solo", Witness(_accepting_verifier()))
    net.broadcast(_make_msg(tree_size=1))
    assert net.check_quorum(1) is True


def test_check_quorum_n2_one_sees() -> None:
    """N=2: ceil(2/3*2)=2 → 1/2 no alcanza."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("a", Witness(_accepting_verifier()))
    net.register("b", Witness(_rejecting_verifier()))
    net.broadcast(_make_msg(tree_size=2))
    assert net.check_quorum(2) is False


def test_check_quorum_n2_both_see() -> None:
    """N=2: ceil(2/3*2)=2 → 2/2 alcanza."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("a", Witness(_accepting_verifier()))
    net.register("b", Witness(_accepting_verifier()))
    net.broadcast(_make_msg(tree_size=3))
    assert net.check_quorum(3) is True


def test_check_quorum_n5_three_see() -> None:
    """N=5: ceil(2/3*5)=4 → 3/5 no alcanza."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    for i in range(3):
        net.register(f"ok{i}", Witness(_accepting_verifier()))
    for i in range(2):
        net.register(f"bad{i}", Witness(_rejecting_verifier()))
    net.broadcast(_make_msg(tree_size=5))
    assert net.check_quorum(5) is False


def test_check_quorum_n5_four_see() -> None:
    """N=5: ceil(2/3*5)=4 → 4/5 alcanza."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    for i in range(4):
        net.register(f"ok{i}", Witness(_accepting_verifier()))
    net.register("bad", Witness(_rejecting_verifier()))
    net.broadcast(_make_msg(tree_size=6))
    assert net.check_quorum(6) is True


def test_check_quorum_n10_seven_see() -> None:
    """N=10: ceil(2/3*10)=7 → 7/10 alcanza exactamente."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    for i in range(7):
        net.register(f"ok{i}", Witness(_accepting_verifier()))
    for i in range(3):
        net.register(f"bad{i}", Witness(_rejecting_verifier()))
    net.broadcast(_make_msg(tree_size=10))
    assert net.check_quorum(10) is True


def test_check_quorum_n3_exact_boundary_2() -> None:
    """N=3, exactamente 2 testigos ven → quórum OK (límite exacto)."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    net.register("a", Witness(_accepting_verifier()))
    net.register("b", Witness(_accepting_verifier()))
    net.register("c", Witness(_rejecting_verifier()))
    net.broadcast(_make_msg(tree_size=30))
    assert net.check_quorum(30) is True


def test_check_quorum_n3_all_3_see() -> None:
    """N=3, los 3 testigos ven → quórum OK (sobre el límite)."""
    net = WitnessNetwork(sig_verifier=_accepting_verifier())
    for i in range(3):
        net.register(f"w{i}", Witness(_accepting_verifier()))
    net.broadcast(_make_msg(tree_size=31))
    assert net.check_quorum(31) is True
