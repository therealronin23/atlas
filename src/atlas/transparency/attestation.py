"""ADR-053 T7 — Interfaz de attestation remota estilo RFC 9334 (RATS).

Arquitectura RATS simplificada:
  Attester → produce Quote (evidencia criptográfica de medición)
  Verifier → appraisa Quote contra medición esperada (policy)

Esta impl es software-only. La impl de enclave real (TDX/SEV-SNP) sigue la
misma Protocol interface pero usa el mecanismo de quote de hardware; está
diferida a una fase posterior. Aquí se usa HMAC-SHA256 como firma software,
suficiente para ejercitar el flujo en entornos sin hardware confidencial.

Topologías soportadas (RFC 9334 §5):
  - Background-Check: el Relying Party recibe el Quote y llama al Verifier
    directamente (AttestedInspector implementa este flujo).
  - Passport: el Attester obtiene el Attestation Result y lo presenta; no
    implementado en este módulo (diferido).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from atlas.security.authorization import HMACSigner, HMACVerifier, SigVerifier, Signer


# ---------------------------------------------------------------------------
# Quote — evidencia criptográfica de medición (RFC 9334 §3.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quote:
    """Evidencia de medición producida por un Attester.

    Atributos:
        measurement: hash hex-string del estado del software medido.
        signature: firma de ``measurement`` en bytes (HMAC o hardware).
        algo: algoritmo de firma usado (informativo; el Verifier decide qué
              acepta según su política).
    """

    measurement: str
    signature: str
    algo: str = "hmac-sha256"


# ---------------------------------------------------------------------------
# Protocol AttestationProvider (RFC 9334 roles Attester + Verifier)
# ---------------------------------------------------------------------------


@runtime_checkable
class AttestationProvider(Protocol):
    """Protocol RFC 9334 RATS: produce y valida evidencia de medición.

    Implementaciones concretas:
      - SoftwareAttestationProvider (esta lib, sin hardware).
      - TDXAttestationProvider / SEVSNPAttestationProvider (diferidos).
    """

    def attest(self) -> Quote:
        """Produce un Quote firmado con la medición del software en ejecución."""
        ...

    def appraise(self, quote: Quote, expected_measurement: str) -> bool:
        """Verifica Quote contra la medición esperada (policy).

        Devuelve True sólo si la firma es válida Y measurement == expected.
        Política fail-closed: cualquier excepción interna → False.
        """
        ...


# ---------------------------------------------------------------------------
# SoftwareAttestationProvider — impl ejercitable sin hardware
# ---------------------------------------------------------------------------


class SoftwareAttestationProvider:
    """Impl software de AttestationProvider (HMAC-SHA256).

    El ``measurement`` representa la «imagen del build»: en prod se derivaría
    del hash del binario o de los artefactos de build reproducible; aquí se
    inyecta en el constructor para que los tests puedan comparar valores
    conocidos.

    La firma HMAC-SHA256 demuestra que el Quote proviene de quien conoce la
    clave secreta compartida. En una impl de hardware (TDX/SEV-SNP), la firma
    la produce el microcode del enclave con una clave derivada de la plataforma;
    la interface Protocol no cambia.
    """

    algo = "hmac-sha256"

    def __init__(
        self,
        measurement: str,
        secret_key: bytes,
        *,
        signer: Signer | None = None,
        verifier: SigVerifier | None = None,
    ) -> None:
        """
        Args:
            measurement: valor de medición del build (hex-string o cualquier str).
            secret_key: clave HMAC compartida entre Attester y Verifier.
            signer: implementación de Signer (por defecto HMACSigner(secret_key)).
            verifier: implementación de SigVerifier (por defecto HMACVerifier(secret_key)).
        """
        self._measurement = measurement
        self._signer: Signer = signer if signer is not None else HMACSigner(secret_key)
        self._verifier: SigVerifier = verifier if verifier is not None else HMACVerifier(secret_key)

    # -- Attester role --

    def attest(self) -> Quote:
        """Produce Quote firmado con el Signer inyectado (por defecto HMAC-SHA256)."""
        payload = self._measurement.encode()
        sig = self._signer.sign(payload)
        return Quote(measurement=self._measurement, signature=sig, algo=self._signer.algo)

    # -- Verifier role --

    def appraise(self, quote: Quote, expected_measurement: str) -> bool:
        """Appraisa Quote: verifica firma y compara measurement. Fail-closed."""
        try:
            # 1. Verificar firma via SigVerifier inyectado
            payload = quote.measurement.encode()
            if not self._verifier.verify(payload, quote.signature):
                return False
            # 2. Verificar que measurement coincide con la política esperada
            return quote.measurement == expected_measurement
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# AttestedInspector — Relying Party (topología Background-Check RFC 9334 §5.1)
# ---------------------------------------------------------------------------


class AttestationError(Exception):
    """Lanzada por AttestedInspector cuando la appraisal falla."""


class AttestedInspector:
    """Inspector que rechaza operar si la attestation del proveedor falla.

    Implementa el rol de *Relying Party* en la topología Background-Check de
    RFC 9334: obtiene el Quote del Attester, lo envía al Verifier (ambos roles
    en AttestationProvider) y sólo procede si la appraisal es positiva.

    Uso::

        provider = SoftwareAttestationProvider(
            measurement="sha256:abcdef...",
            secret_key=b"secret",
        )
        inspector = AttestedInspector(
            provider=provider,
            expected_measurement="sha256:abcdef...",
        )
        result = inspector.inspect("recurso")  # opera sólo si appraisal OK
    """

    def __init__(
        self,
        provider: AttestationProvider,
        expected_measurement: str,
    ) -> None:
        self._provider = provider
        self._expected = expected_measurement

    def inspect(self, resource: Any) -> str:
        """Intenta inspeccionar ``resource`` previa attestation.

        Raises:
            AttestationError: si la appraisal falla (measurement incorrecto o
                              firma inválida). No opera sobre el recurso.

        Returns:
            Cadena descriptiva del resultado de inspección (demo).
        """
        quote = self._provider.attest()
        if not self._provider.appraise(quote, self._expected):
            raise AttestationError(
                f"Attestation fallida: measurement={quote.measurement!r} "
                f"no coincide con expected={self._expected!r} "
                f"o la firma es inválida."
            )
        return f"inspeccionado:{resource}"
