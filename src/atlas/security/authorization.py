"""ADR-043 Fase 0 — Gate de autorización verificable.

Armadura sin capacidad ofensiva: define Capability, TargetSpec, firmas
enchufables (HMAC-stdlib + ed25519 opcional), AuthorizationGrant y
AuthorizationVerifier con política fail-closed.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Capability enum
# ---------------------------------------------------------------------------

class Capability(str, Enum):
    SCAN = "SCAN"
    PROBE = "PROBE"
    EXPLOIT_POC = "EXPLOIT_POC"
    FUZZ = "FUZZ"


# ---------------------------------------------------------------------------
# TargetSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetSpec:
    value: str
    kind: str  # "host" | "cidr"

    def matches(self, candidate: str) -> bool:
        """Comprueba si candidate está cubierto por este spec. Fail-closed."""
        try:
            if self.kind == "host":
                return self._match_host(candidate)
            elif self.kind == "cidr":
                return self._match_cidr(candidate)
            return False
        except Exception:
            return False

    def _match_host(self, candidate: str) -> bool:
        # Separar host y puerto de value y candidate
        spec_host, spec_port = _split_host_port(self.value)
        cand_host, cand_port = _split_host_port(candidate)
        if spec_host != cand_host:
            return False
        if spec_port is None:
            # sin puerto en spec → matchea cualquier puerto del mismo host
            return True
        # spec tiene puerto → exige igualdad
        return spec_port == cand_port

    def _match_cidr(self, candidate: str) -> bool:
        # Extraer solo la IP (sin puerto)
        cand_host, _ = _split_host_port(candidate)
        ip = ipaddress.ip_address(cand_host)
        net = ipaddress.ip_network(self.value, strict=False)
        return ip in net


def _split_host_port(addr: str) -> tuple[str, str | None]:
    """Devuelve (host, port_str|None). Soporta IPv6 [::1]:port."""
    if addr.startswith("["):
        # IPv6 con corchetes: [::1]:8080 o [::1]
        bracket_end = addr.index("]")
        host = addr[1:bracket_end]
        rest = addr[bracket_end + 1:]
        port = rest[1:] if rest.startswith(":") else None
        return host, port
    if ":" in addr:
        parts = addr.rsplit(":", 1)
        # Si la parte derecha es numérica, es un puerto
        if parts[1].isdigit():
            return parts[0], parts[1]
    return addr, None


# ---------------------------------------------------------------------------
# Protocolo de firma enchufable
# ---------------------------------------------------------------------------

@runtime_checkable
class Signer(Protocol):
    algo: str

    def sign(self, payload: bytes) -> str:
        ...


@runtime_checkable
class SigVerifier(Protocol):
    algo: str

    def verify(self, payload: bytes, signature: str) -> bool:
        ...


# HMAC-SHA256 (stdlib, sin deps extra)

class HMACSigner:
    algo = "hmac-sha256"

    def __init__(self, key: bytes) -> None:
        self._key = key

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()


class HMACVerifier:
    algo = "hmac-sha256"

    def __init__(self, key: bytes) -> None:
        self._key = key

    def verify(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


# Ed25519 (import perezoso; optional dep)

class Ed25519Signer:
    algo = "ed25519"

    def __init__(self, private_key_bytes: bytes) -> None:
        self._raw = private_key_bytes

    def sign(self, payload: bytes) -> str:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError as exc:
            raise RuntimeError(
                "cryptography no instalado; usa hmac-sha256"
            ) from exc
        key = Ed25519PrivateKey.from_private_bytes(self._raw)
        sig = key.sign(payload)
        return sig.hex()


class Ed25519Verifier:
    algo = "ed25519"

    def __init__(self, public_key_bytes: bytes) -> None:
        self._raw = public_key_bytes

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ImportError as exc:
            raise RuntimeError(
                "cryptography no instalado; usa hmac-sha256"
            ) from exc
        key = Ed25519PublicKey.from_public_bytes(self._raw)
        try:
            key.verify(bytes.fromhex(signature), payload)
            return True
        except Exception:
            return False


def verifier_for(
    algo: str,
    *,
    hmac_key: bytes | None = None,
    ed25519_public: bytes | None = None,
) -> SigVerifier:
    """Factory de verifiers por nombre de algoritmo."""
    if algo == "hmac-sha256":
        if hmac_key is None:
            raise ValueError("hmac_key requerida para hmac-sha256")
        return HMACVerifier(hmac_key)
    if algo == "ed25519":
        if ed25519_public is None:
            raise ValueError("ed25519_public requerida para ed25519")
        return Ed25519Verifier(ed25519_public)
    raise ValueError(f"algoritmo desconocido: {algo!r}")


# ---------------------------------------------------------------------------
# AuthorizationGrant
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuthorizationGrant:
    target: TargetSpec
    capability: Capability
    expires_at: str  # ISO-8601 UTC
    issuer: str
    algo: str
    signature: str

    def signed_payload(self) -> bytes:
        """JSON determinista (sin signature) → UTF-8."""
        doc = {
            "target": {"value": self.target.value, "kind": self.target.kind},
            "capability": self.capability.value,
            "expires_at": self.expires_at,
            "issuer": self.issuer,
            "algo": self.algo,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def issue(
        cls,
        *,
        target: TargetSpec,
        capability: Capability,
        expires_at: str,
        issuer: str,
        signer: Signer,
    ) -> "AuthorizationGrant":
        # Construir instancia temporal sin firma para calcular payload
        draft = cls(
            target=target,
            capability=capability,
            expires_at=expires_at,
            issuer=issuer,
            algo=signer.algo,
            signature="",
        )
        sig = signer.sign(draft.signed_payload())
        return cls(
            target=target,
            capability=capability,
            expires_at=expires_at,
            issuer=issuer,
            algo=signer.algo,
            signature=sig,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """Fail-closed: parse fallido → True."""
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            ref = now if now is not None else datetime.now(timezone.utc)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            return ref >= exp
        except Exception:
            return True


# ---------------------------------------------------------------------------
# AuthorizationDecision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


# ---------------------------------------------------------------------------
# AuthorizationVerifier
# ---------------------------------------------------------------------------

class AuthorizationVerifier:
    def __init__(
        self,
        *,
        hmac_key: bytes | None = None,
        ed25519_public: bytes | None = None,
    ) -> None:
        self._hmac_key = hmac_key
        self._ed25519_public = ed25519_public

    def check(
        self,
        grant: AuthorizationGrant,
        *,
        candidate_target: str,
        capability: Capability,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Gate fail-closed. Cada paso fallido devuelve Deny con reason específico."""
        # a) Obtener verifier
        try:
            verifier = verifier_for(
                grant.algo,
                hmac_key=self._hmac_key,
                ed25519_public=self._ed25519_public,
            )
        except ValueError:
            return AuthorizationDecision(allowed=False, reason="sin clave de verificación")

        # b) Verificar firma
        try:
            sig_ok = verifier.verify(grant.signed_payload(), grant.signature)
        except Exception:
            sig_ok = False
        if not sig_ok:
            return AuthorizationDecision(allowed=False, reason="firma inválida")

        # c) Expiración
        if grant.is_expired(now):
            return AuthorizationDecision(allowed=False, reason="grant caducado")

        # d) Capacidad
        if grant.capability != capability:
            return AuthorizationDecision(allowed=False, reason="capacidad no cubierta")

        # e) Target
        if not grant.target.matches(candidate_target):
            return AuthorizationDecision(allowed=False, reason="target fuera de scope")

        return AuthorizationDecision(allowed=True, reason="autorizado")
