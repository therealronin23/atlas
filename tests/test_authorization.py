"""Tests ADR-043 Fase 0 — AuthorizationGrant / AuthorizationVerifier / wiring seam.

Sin red, sin targets reales, sin cryptography obligatorio.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.security.authorization import (
    AuthorizationDecision,
    AuthorizationGrant,
    AuthorizationVerifier,
    Capability,
    HMACSigner,
    HMACVerifier,
    TargetSpec,
    verifier_for,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KEY = b"test-secret-key-abc"
ISSUER = "test-issuer"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _grant(
    *,
    target_value: str = "192.168.1.1",
    target_kind: str = "host",
    capability: Capability = Capability.SCAN,
    expires_at: str | None = None,
    key: bytes = KEY,
) -> AuthorizationGrant:
    return AuthorizationGrant.issue(
        target=TargetSpec(value=target_value, kind=target_kind),
        capability=capability,
        expires_at=expires_at or _future(),
        issuer=ISSUER,
        signer=HMACSigner(key),
    )


def _verifier(key: bytes = KEY) -> AuthorizationVerifier:
    return AuthorizationVerifier(hmac_key=key)


# ---------------------------------------------------------------------------
# HMAC roundtrip OK
# ---------------------------------------------------------------------------

def test_hmac_roundtrip_allowed() -> None:
    grant = _grant()
    dec = _verifier().check(grant, candidate_target="192.168.1.1", capability=Capability.SCAN)
    assert dec.allowed
    assert dec.reason == "autorizado"


# ---------------------------------------------------------------------------
# Grant manipulado → firma inválida
# ---------------------------------------------------------------------------

def test_tampered_target_invalid_signature() -> None:
    grant = _grant(target_value="192.168.1.1")
    # Reemplazamos target por otro; la firma ya no corresponde
    tampered = AuthorizationGrant(
        target=TargetSpec(value="10.0.0.1", kind="host"),
        capability=grant.capability,
        expires_at=grant.expires_at,
        issuer=grant.issuer,
        algo=grant.algo,
        signature=grant.signature,  # firma del grant original
    )
    dec = _verifier().check(tampered, candidate_target="10.0.0.1", capability=Capability.SCAN)
    assert not dec.allowed
    assert dec.reason == "firma inválida"


def test_tampered_capability_invalid_signature() -> None:
    grant = _grant(capability=Capability.SCAN)
    tampered = AuthorizationGrant(
        target=grant.target,
        capability=Capability.EXPLOIT_POC,  # distinto
        expires_at=grant.expires_at,
        issuer=grant.issuer,
        algo=grant.algo,
        signature=grant.signature,
    )
    dec = _verifier().check(tampered, candidate_target="192.168.1.1", capability=Capability.EXPLOIT_POC)
    assert not dec.allowed
    assert dec.reason == "firma inválida"


# ---------------------------------------------------------------------------
# Grant caducado
# ---------------------------------------------------------------------------

def test_expired_grant_denied() -> None:
    grant = _grant(expires_at=_past())
    dec = _verifier().check(grant, candidate_target="192.168.1.1", capability=Capability.SCAN)
    assert not dec.allowed
    assert dec.reason == "grant caducado"


# ---------------------------------------------------------------------------
# Capacidad distinta
# ---------------------------------------------------------------------------

def test_wrong_capability_denied() -> None:
    grant = _grant(capability=Capability.SCAN)
    dec = _verifier().check(grant, candidate_target="192.168.1.1", capability=Capability.FUZZ)
    assert not dec.allowed
    assert dec.reason == "capacidad no cubierta"


# ---------------------------------------------------------------------------
# TargetSpec host: exacto / host:port / fuera de scope
# ---------------------------------------------------------------------------

def test_target_host_exact_match() -> None:
    spec = TargetSpec(value="example.com", kind="host")
    assert spec.matches("example.com")


def test_target_host_no_port_matches_any_port() -> None:
    spec = TargetSpec(value="example.com", kind="host")
    assert spec.matches("example.com:443")
    assert spec.matches("example.com:8080")


def test_target_host_with_port_exact() -> None:
    spec = TargetSpec(value="example.com:443", kind="host")
    assert spec.matches("example.com:443")
    assert not spec.matches("example.com:8080")
    assert not spec.matches("example.com")


def test_target_host_different_host_no_match() -> None:
    spec = TargetSpec(value="example.com", kind="host")
    assert not spec.matches("evil.com")


# ---------------------------------------------------------------------------
# TargetSpec CIDR
# ---------------------------------------------------------------------------

def test_target_cidr_match() -> None:
    spec = TargetSpec(value="192.168.1.0/24", kind="cidr")
    assert spec.matches("192.168.1.50")
    assert spec.matches("192.168.1.50:443")


def test_target_cidr_no_match() -> None:
    spec = TargetSpec(value="192.168.1.0/24", kind="cidr")
    assert not spec.matches("10.0.0.1")


def test_target_cidr_invalid_candidate_fail_closed() -> None:
    spec = TargetSpec(value="192.168.1.0/24", kind="cidr")
    assert not spec.matches("not-an-ip")


# ---------------------------------------------------------------------------
# verifier_for: algo desconocido → ValueError
# ---------------------------------------------------------------------------

def test_verifier_for_unknown_algo_raises() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        verifier_for("rsa-pkcs1")


def test_verifier_for_hmac_without_key_raises() -> None:
    with pytest.raises(ValueError):
        verifier_for("hmac-sha256")


# ---------------------------------------------------------------------------
# Sin clave HMAC → fail-closed
# ---------------------------------------------------------------------------

def test_no_hmac_key_fail_closed() -> None:
    grant = _grant()
    verifier = AuthorizationVerifier(hmac_key=None)
    dec = verifier.check(grant, candidate_target="192.168.1.1", capability=Capability.SCAN)
    assert not dec.allowed
    assert "sin clave" in dec.reason


# ---------------------------------------------------------------------------
# Ed25519 (opcional; skip si cryptography no está)
# ---------------------------------------------------------------------------

def test_ed25519_roundtrip() -> None:
    cryptography = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from atlas.security.authorization import Ed25519Signer, Ed25519Verifier

    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes_raw()
    pub_bytes = private_key.public_key().public_bytes_raw()

    signer = Ed25519Signer(priv_bytes)
    grant = AuthorizationGrant.issue(
        target=TargetSpec(value="10.0.0.1", kind="host"),
        capability=Capability.PROBE,
        expires_at=_future(),
        issuer="ed25519-issuer",
        signer=signer,
    )
    verifier = AuthorizationVerifier(ed25519_public=pub_bytes)
    dec = verifier.check(grant, candidate_target="10.0.0.1", capability=Capability.PROBE)
    assert dec.allowed


def test_ed25519_tamper_denied() -> None:
    cryptography = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from atlas.security.authorization import Ed25519Signer, Ed25519Verifier

    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes_raw()
    pub_bytes = private_key.public_key().public_bytes_raw()

    signer = Ed25519Signer(priv_bytes)
    grant = AuthorizationGrant.issue(
        target=TargetSpec(value="10.0.0.1", kind="host"),
        capability=Capability.PROBE,
        expires_at=_future(),
        issuer="ed25519-issuer",
        signer=signer,
    )
    tampered = AuthorizationGrant(
        target=TargetSpec(value="10.0.0.2", kind="host"),
        capability=grant.capability,
        expires_at=grant.expires_at,
        issuer=grant.issuer,
        algo=grant.algo,
        signature=grant.signature,
    )
    verifier = AuthorizationVerifier(ed25519_public=pub_bytes)
    dec = verifier.check(tampered, candidate_target="10.0.0.2", capability=Capability.PROBE)
    assert not dec.allowed
    assert dec.reason == "firma inválida"


# ---------------------------------------------------------------------------
# Wiring del seam: authorize_offensive_action
# ---------------------------------------------------------------------------

@pytest.fixture
def orch(tmp_path: Path, monkeypatch):
    import atlas.governance.governance_l0 as g
    g.GovernanceL0._instance = None
    ws = tmp_path / "atlas"
    ws.mkdir()
    from atlas.core.orchestrator import Orchestrator
    o = Orchestrator(workspace=ws)
    yield o
    g.GovernanceL0._instance = None


def test_no_grant_denied_without_decider_call(orch, monkeypatch) -> None:
    """Sin grant válido (firma errónea), el gate deniega antes de consultar el decisor."""
    from atlas.core.decider.autonomous_decider import AutonomousDecider
    from atlas.core.decider.decider import Deny

    decider_calls: list = []
    original_decide = AutonomousDecider.decide

    def tracking_decide(self, action, *, sanctioned_intent, context):
        decider_calls.append(action)
        return original_decide(self, action, sanctioned_intent=sanctioned_intent, context=context)

    monkeypatch.setattr(AutonomousDecider, "decide", tracking_decide)
    orch.set_decider(AutonomousDecider())

    # grant con firma falsa
    bad_grant = AuthorizationGrant(
        target=TargetSpec(value="192.168.1.1", kind="host"),
        capability=Capability.SCAN,
        expires_at=_future(),
        issuer="attacker",
        algo="hmac-sha256",
        signature="deadbeef",
    )

    monkeypatch.setenv("ATLAS_AUTHZ_HMAC_KEY", KEY.decode())
    result, _ = orch.authorize_offensive_action(
        bad_grant,
        candidate_target="192.168.1.1",
        capability=Capability.SCAN,
        intent="scan target",
        contained=True,
    )

    from atlas.core.decider.decider import Deny as _Deny
    assert isinstance(result, _Deny)
    assert "sin autorización" in result.reason
    assert decider_calls == []  # el decisor no fue consultado


def test_valid_grant_contained_false_reaches_decider_with_high_sensitivity(
    orch, monkeypatch
) -> None:
    """Grant válido + contained=False → DecisionAction llega al decisor con reversible=False, sensitivity=high."""
    from atlas.core.decider.decider import DecisionAction, Deny

    received_actions: list[DecisionAction] = []

    class CapturingDecider:
        def decide(self, action: DecisionAction, *, sanctioned_intent, context):
            received_actions.append(action)
            return Deny(reason="capturado")

    orch.set_decider(CapturingDecider())  # type: ignore[arg-type]

    grant = _grant(target_value="192.168.1.1", target_kind="host", capability=Capability.SCAN)

    monkeypatch.setenv("ATLAS_AUTHZ_HMAC_KEY", KEY.decode())
    result, _ = orch.authorize_offensive_action(
        grant,
        candidate_target="192.168.1.1",
        capability=Capability.SCAN,
        intent="offensive scan",
        contained=False,
    )

    assert len(received_actions) == 1
    action = received_actions[0]
    assert action.kind == "offensive_action"
    assert action.reversible is False
    assert action.sensitivity == "high"
    assert "SCAN" in action.descriptor


def test_valid_grant_contained_true_reversible(orch, monkeypatch) -> None:
    """Grant válido + contained=True → reversible=True, sensitivity=moderate."""
    from atlas.core.decider.decider import DecisionAction, Deny

    received_actions: list[DecisionAction] = []

    class CapturingDecider:
        def decide(self, action: DecisionAction, *, sanctioned_intent, context):
            received_actions.append(action)
            return Deny(reason="capturado")

    orch.set_decider(CapturingDecider())  # type: ignore[arg-type]

    grant = _grant(capability=Capability.FUZZ)
    monkeypatch.setenv("ATLAS_AUTHZ_HMAC_KEY", KEY.decode())
    orch.authorize_offensive_action(
        grant,
        candidate_target="192.168.1.1",
        capability=Capability.FUZZ,
        intent="fuzz target",
        contained=True,
    )

    assert received_actions[0].reversible is True
    assert received_actions[0].sensitivity == "moderate"


# ---------------------------------------------------------------------------
# Tests de integración: authorize_offensive_action escribe en Merkle
# ---------------------------------------------------------------------------

def test_denied_grant_writes_merkle_with_reason_and_grant(orch, monkeypatch) -> None:
    """Grant con firma inválida → Merkle registra authz.denied con reason y grant serializado."""
    monkeypatch.setenv("ATLAS_AUTHZ_HMAC_KEY", KEY.decode())

    bad_grant = AuthorizationGrant(
        target=TargetSpec(value="192.168.1.1", kind="host"),
        capability=Capability.SCAN,
        expires_at=_future(),
        issuer="attacker",
        algo="hmac-sha256",
        signature="deadbeef",
    )

    orch.authorize_offensive_action(
        bad_grant,
        candidate_target="192.168.1.1",
        capability=Capability.SCAN,
        intent="test",
        contained=True,
    )

    records = orch._merkle.tail(5)
    last = records[-1]
    assert last.action == "authz.denied"
    assert last.result == "blocked"
    assert "reason" in last.payload
    assert "grant" in last.payload
    grant_dict = last.payload["grant"]
    assert "issuer" in grant_dict
    assert "capability" in grant_dict


def test_valid_grant_writes_merkle_with_grant_fields(orch, monkeypatch) -> None:
    """Grant válido → Merkle registra authz.granted con grant serializado (issuer, capability)."""
    monkeypatch.setenv("ATLAS_AUTHZ_HMAC_KEY", KEY.decode())

    from atlas.core.decider.decider import DecisionAction, Deny

    class CapturingDecider:
        def decide(self, action: DecisionAction, *, sanctioned_intent, context):
            return Deny(reason="capturado")

    orch.set_decider(CapturingDecider())  # type: ignore[arg-type]

    valid_grant = _grant(target_value="192.168.1.1", target_kind="host", capability=Capability.SCAN)

    orch.authorize_offensive_action(
        valid_grant,
        candidate_target="192.168.1.1",
        capability=Capability.SCAN,
        intent="test",
        contained=True,
    )

    records = orch._merkle.tail(10)
    authz_record = next((r for r in reversed(records) if r.action == "authz.granted"), None)
    assert authz_record is not None, "No se encontró registro authz.granted en Merkle"
    assert authz_record.result == "success"
    assert "grant" in authz_record.payload
    grant_dict = authz_record.payload["grant"]
    assert grant_dict["issuer"] == ISSUER
    assert "SCAN" in grant_dict["capability"]
