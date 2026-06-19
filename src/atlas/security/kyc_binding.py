"""KYC binding for device-bound access control.

This module binds a verified identity claim to a device fingerprint. It does not
perform document, liveness, sanctions, or legal residency checks itself; those
remain the responsibility of the injected identity verifier.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlas.security.authorization import SigVerifier, Signer


@dataclass(frozen=True)
class IdentityClaim:
    """Identity claim to verify with an external KYC provider."""

    subject_id: str
    residency: str          # ISO-3166 alpha-2, for example "ES" or "US".
    evidence_ref: str = ""  # Opaque reference to KYC evidence; do not store raw PII.


@dataclass(frozen=True)
class KycBinding:
    """Signed device fingerprint to verified identity binding."""

    device_fingerprint: str
    subject_id: str
    residency: str
    evidence_ref: str
    issuer_id: str
    policy_version: str
    issued_at_ns: int
    expires_at_ns: int | None
    signature: str

    def signing_body(self) -> bytes:
        return json.dumps(
            {
                "device_fingerprint": self.device_fingerprint,
                "evidence_ref": self.evidence_ref,
                "expires_at_ns": self.expires_at_ns,
                "issued_at_ns": self.issued_at_ns,
                "issuer_id": self.issuer_id,
                "policy_version": self.policy_version,
                "residency": self.residency,
                "subject_id": self.subject_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()


@runtime_checkable
class IdentityVerifier(Protocol):
    """Pluggable identity verifier implemented by a real KYC provider."""

    def verify(self, claim: IdentityClaim) -> bool:
        ...


class AllowlistIdentityVerifier:
    """Software stub accepting subject ids from an allowlist."""

    def __init__(self, allowed_subject_ids: frozenset[str]) -> None:
        self._allowed = allowed_subject_ids

    def verify(self, claim: IdentityClaim) -> bool:
        return bool(claim.subject_id) and claim.subject_id in self._allowed


class KycRejected(Exception):
    """Identity verification or residency policy failed."""


class KycBinder:
    """Issue and verify device-to-identity bindings.

    Args:
        verifier: Identity verifier.
        issuer_signer: Binding issuer signer.
        residency_policy: Predicate over residency code. Defaults to allow all.
        issuer_id: Stable issuer identifier included in the signed body.
        policy_version: Policy version included in the signed body.
        validity_ns: Optional validity window. None means no binding expiration.
        clock: Injectable nanosecond clock for tests.
    """

    def __init__(
        self,
        verifier: IdentityVerifier,
        issuer_signer: Signer,
        *,
        residency_policy: Callable[[str], bool] | None = None,
        issuer_id: str = "atlas.local",
        policy_version: str = "default",
        validity_ns: int | None = None,
        clock: Callable[[], int] = time.time_ns,
    ) -> None:
        self._verifier = verifier
        self._signer = issuer_signer
        self._residency_policy = residency_policy or (lambda _r: True)
        self._issuer_id = issuer_id
        self._policy_version = policy_version
        self._validity_ns = validity_ns
        self._clock = clock

    def bind(self, device_fingerprint: str, claim: IdentityClaim) -> KycBinding:
        """Issue a signed binding, failing closed with KycRejected."""
        if not device_fingerprint:
            raise KycRejected("empty device_fingerprint")
        residency = claim.residency.upper()
        if len(residency) != 2 or not residency.isalpha():
            raise KycRejected(f"invalid residency code: {claim.residency!r}")
        if not self._verifier.verify(claim):
            raise KycRejected(f"identidad no verificada para subject_id={claim.subject_id!r}")
        if not self._residency_policy(residency):
            raise KycRejected(f"residencia {residency!r} no permitida por política")
        issued_at_ns = self._clock()
        expires_at_ns = (
            issued_at_ns + self._validity_ns
            if self._validity_ns is not None
            else None
        )
        draft = KycBinding(
            device_fingerprint=device_fingerprint,
            subject_id=claim.subject_id,
            residency=residency,
            evidence_ref=claim.evidence_ref,
            issuer_id=self._issuer_id,
            policy_version=self._policy_version,
            issued_at_ns=issued_at_ns,
            expires_at_ns=expires_at_ns,
            signature="",
        )
        sig = self._signer.sign(draft.signing_body())
        return KycBinding(
            device_fingerprint=device_fingerprint,
            subject_id=claim.subject_id,
            residency=residency,
            evidence_ref=claim.evidence_ref,
            issuer_id=self._issuer_id,
            policy_version=self._policy_version,
            issued_at_ns=draft.issued_at_ns,
            expires_at_ns=draft.expires_at_ns,
            signature=sig,
        )

    @staticmethod
    def verify_binding(
        binding: KycBinding,
        issuer_verifier: SigVerifier,
        *,
        clock: Callable[[], int] = time.time_ns,
    ) -> bool:
        """Verify issuer signature and binding expiry."""
        try:
            if binding.expires_at_ns is not None and clock() > binding.expires_at_ns:
                return False
            return issuer_verifier.verify(binding.signing_body(), binding.signature)
        except Exception:  # noqa: BLE001
            return False
