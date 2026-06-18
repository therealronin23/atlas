"""Tests para ADR-053 T7 — AttestationProvider y AttestedInspector.

Cubre:
  - Quote es un dataclass inmutable con measurement y signature.
  - SoftwareAttestationProvider implementa el Protocol AttestationProvider.
  - attest() produce Quote con measurement y firma válida.
  - appraise() devuelve True cuando measurement y firma son correctos.
  - appraise() devuelve False cuando measurement no coincide con expected.
  - appraise() devuelve False cuando la firma está adulterada.
  - AttestedInspector deja operar si appraisal OK.
  - AttestedInspector bloquea (AttestationError) si appraisal falla.
"""

import pytest

from atlas.transparency.attestation import (
    AttestationError,
    AttestationProvider,
    AttestedInspector,
    Quote,
    SoftwareAttestationProvider,
)

SECRET = b"clave-secreta-para-tests"
MEASUREMENT_OK = "sha256:cafebabe"
MEASUREMENT_MALO = "sha256:deadbeef"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider() -> SoftwareAttestationProvider:
    return SoftwareAttestationProvider(
        measurement=MEASUREMENT_OK,
        secret_key=SECRET,
    )


@pytest.fixture()
def inspector(provider: SoftwareAttestationProvider) -> AttestedInspector:
    return AttestedInspector(provider=provider, expected_measurement=MEASUREMENT_OK)


# ---------------------------------------------------------------------------
# Quote dataclass
# ---------------------------------------------------------------------------


def test_quote_es_inmutable() -> None:
    q = Quote(measurement="m", signature="7369670000")
    with pytest.raises((AttributeError, TypeError)):
        q.measurement = "otro"  # type: ignore[misc]


def test_quote_tiene_campos_minimos() -> None:
    q = Quote(measurement="m", signature="7369670000")
    assert q.measurement == "m"
    assert q.signature == "7369670000"
    assert isinstance(q.algo, str)


# ---------------------------------------------------------------------------
# SoftwareAttestationProvider cumple el Protocol
# ---------------------------------------------------------------------------


def test_software_provider_cumple_protocol(provider: SoftwareAttestationProvider) -> None:
    assert isinstance(provider, AttestationProvider)


# ---------------------------------------------------------------------------
# attest()
# ---------------------------------------------------------------------------


def test_attest_devuelve_quote_con_measurement_correcto(
    provider: SoftwareAttestationProvider,
) -> None:
    quote = provider.attest()
    assert quote.measurement == MEASUREMENT_OK


def test_attest_devuelve_quote_con_signature_no_vacia(
    provider: SoftwareAttestationProvider,
) -> None:
    quote = provider.attest()
    assert len(quote.signature) > 0


def test_attest_firma_es_determinista_con_misma_clave(
    provider: SoftwareAttestationProvider,
) -> None:
    q1 = provider.attest()
    q2 = provider.attest()
    assert q1.signature == q2.signature


# ---------------------------------------------------------------------------
# appraise() — caso OK
# ---------------------------------------------------------------------------


def test_appraise_ok_cuando_measurement_y_firma_correctos(
    provider: SoftwareAttestationProvider,
) -> None:
    quote = provider.attest()
    assert provider.appraise(quote, MEASUREMENT_OK) is True


# ---------------------------------------------------------------------------
# appraise() — measurement no coincide con expected
# ---------------------------------------------------------------------------


def test_appraise_falla_si_expected_measurement_distinto(
    provider: SoftwareAttestationProvider,
) -> None:
    quote = provider.attest()
    # Quote tiene MEASUREMENT_OK pero esperamos MEASUREMENT_MALO
    assert provider.appraise(quote, MEASUREMENT_MALO) is False


def test_appraise_falla_si_quote_measurement_adulterado(
    provider: SoftwareAttestationProvider,
) -> None:
    quote_real = provider.attest()
    # Adulteramos el measurement manteniendo la firma original → falla firma
    quote_adulterado = Quote(
        measurement=MEASUREMENT_MALO,
        signature=quote_real.signature,  # firma sigue siendo str hex
        algo=quote_real.algo,
    )
    assert provider.appraise(quote_adulterado, MEASUREMENT_MALO) is False


# ---------------------------------------------------------------------------
# appraise() — firma inválida
# ---------------------------------------------------------------------------


def test_appraise_falla_si_firma_incorrecta(
    provider: SoftwareAttestationProvider,
) -> None:
    quote = provider.attest()
    quote_mal_firmado = Quote(
        measurement=quote.measurement,
        signature="00" * 32,  # firma basura (hex str de 32 bytes de ceros)
        algo=quote.algo,
    )
    assert provider.appraise(quote_mal_firmado, MEASUREMENT_OK) is False


def test_appraise_falla_con_firma_de_clave_distinta() -> None:
    provider_a = SoftwareAttestationProvider(MEASUREMENT_OK, b"clave-A")
    provider_b = SoftwareAttestationProvider(MEASUREMENT_OK, b"clave-B")
    quote_de_a = provider_a.attest()
    # provider_b tiene misma measurement pero distinta clave → firma inválida
    assert provider_b.appraise(quote_de_a, MEASUREMENT_OK) is False


# ---------------------------------------------------------------------------
# AttestedInspector — deja operar si appraisal OK
# ---------------------------------------------------------------------------


def test_inspector_opera_con_appraisal_correcta(
    inspector: AttestedInspector,
) -> None:
    result = inspector.inspect("recurso-test")
    assert "recurso-test" in result


# ---------------------------------------------------------------------------
# AttestedInspector — bloquea si appraisal falla
# ---------------------------------------------------------------------------


def test_inspector_bloquea_si_measurement_no_coincide() -> None:
    provider = SoftwareAttestationProvider(MEASUREMENT_OK, SECRET)
    # El inspector espera MEASUREMENT_MALO, pero el provider reporta MEASUREMENT_OK
    inspector = AttestedInspector(
        provider=provider,
        expected_measurement=MEASUREMENT_MALO,
    )
    with pytest.raises(AttestationError):
        inspector.inspect("recurso")


def test_inspector_bloquea_si_firma_invalida() -> None:
    """Inspector bloquea cuando el provider firma con clave distinta a la que verifica."""

    class TamperedProvider:
        """Attester que firma con clave A pero verifica con clave B → siempre falla."""

        def attest(self) -> Quote:
            signer = SoftwareAttestationProvider(MEASUREMENT_OK, b"clave-A")
            return signer.attest()

        def appraise(self, quote: Quote, expected_measurement: str) -> bool:
            verifier = SoftwareAttestationProvider(MEASUREMENT_OK, b"clave-B")
            return verifier.appraise(quote, expected_measurement)

    inspector = AttestedInspector(
        provider=TamperedProvider(),
        expected_measurement=MEASUREMENT_OK,
    )
    with pytest.raises(AttestationError):
        inspector.inspect("recurso")
