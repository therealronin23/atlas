"""KYC binding (GAP-4): binding clave-de-dispositivo ↔ identidad, fail-closed."""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier
from atlas.security.kyc_binding import (
    AllowlistIdentityVerifier,
    IdentityClaim,
    IdentityVerifier,
    KycBinder,
    KycRejected,
)


def _issuer():
    k = Ed25519PrivateKey.generate()
    return Ed25519Signer(k.private_bytes_raw()), Ed25519Verifier(k.public_key().public_bytes_raw())


def test_bind_and_verify_roundtrip():
    signer, verifier = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    binding = binder.bind(
        "fp:abc123",
        IdentityClaim(subject_id="alice", residency="es", evidence_ref="kyc:case-1"),
    )
    assert binding.subject_id == "alice" and binding.residency == "ES"
    assert binding.evidence_ref == "kyc:case-1"
    assert KycBinder.verify_binding(binding, verifier) is True


def test_rejects_unverified_identity():
    signer, _ = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    with pytest.raises(KycRejected):
        binder.bind("fp:abc", IdentityClaim(subject_id="mallory", residency="ES"))


def test_rejects_empty_fingerprint():
    signer, _ = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    with pytest.raises(KycRejected):
        binder.bind("", IdentityClaim(subject_id="alice", residency="ES"))


def test_residency_policy_export_control():
    signer, _ = _issuer()
    # Política de control de exportación: deniega ciertas jurisdicciones.
    policy = lambda r: r not in {"XX", "YY"}
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer,
                       residency_policy=policy)
    with pytest.raises(KycRejected):
        binder.bind("fp:abc", IdentityClaim(subject_id="alice", residency="XX"))
    ok = binder.bind("fp:abc", IdentityClaim(subject_id="alice", residency="ES"))
    assert ok.residency == "ES"


def test_verify_rejects_tampered_binding():
    signer, verifier = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    binding = binder.bind("fp:abc", IdentityClaim(subject_id="alice", residency="ES"))
    tampered = type(binding)(
        device_fingerprint="fp:OTHER", subject_id=binding.subject_id,
        residency=binding.residency, evidence_ref=binding.evidence_ref,
        issuer_id=binding.issuer_id, policy_version=binding.policy_version,
        issued_at_ns=binding.issued_at_ns, expires_at_ns=binding.expires_at_ns,
        signature=binding.signature,
    )
    assert KycBinder.verify_binding(tampered, verifier) is False


def test_verify_rejects_tampered_evidence_ref():
    signer, verifier = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    binding = binder.bind(
        "fp:abc",
        IdentityClaim(subject_id="alice", residency="ES", evidence_ref="kyc:case-1"),
    )
    tampered = type(binding)(
        device_fingerprint=binding.device_fingerprint,
        subject_id=binding.subject_id,
        residency=binding.residency,
        evidence_ref="kyc:case-2",
        issuer_id=binding.issuer_id,
        policy_version=binding.policy_version,
        issued_at_ns=binding.issued_at_ns,
        expires_at_ns=binding.expires_at_ns,
        signature=binding.signature,
    )
    assert KycBinder.verify_binding(tampered, verifier) is False


def test_verify_rejects_expired_binding():
    signer, verifier = _issuer()
    binder = KycBinder(
        AllowlistIdentityVerifier(frozenset({"alice"})),
        signer,
        validity_ns=10,
        clock=lambda: 100,
    )
    binding = binder.bind("fp:abc", IdentityClaim(subject_id="alice", residency="ES"))
    assert KycBinder.verify_binding(binding, verifier, clock=lambda: 105) is True
    assert KycBinder.verify_binding(binding, verifier, clock=lambda: 111) is False


def test_rejects_invalid_residency_code():
    signer, _ = _issuer()
    binder = KycBinder(AllowlistIdentityVerifier(frozenset({"alice"})), signer)
    with pytest.raises(KycRejected):
        binder.bind("fp:abc", IdentityClaim(subject_id="alice", residency="USA"))


def test_stub_implements_protocol():
    assert isinstance(AllowlistIdentityVerifier(frozenset()), IdentityVerifier)
