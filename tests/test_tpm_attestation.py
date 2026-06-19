"""OSM-025 Capa 2: TpmAttestationProvider (presencia TPM + arranque-medido, fail-closed)."""
from __future__ import annotations

import hashlib

import pytest

from atlas.security.authorization import HMACSigner, HMACVerifier
from atlas.transparency.attestation import (
    AttestationProvider,
    Quote,
    TpmAttestationProvider,
    TpmUnavailableError,
)

_KEY = b"shared-tpm-test-key"


def _provider(**kw) -> TpmAttestationProvider:
    return TpmAttestationProvider(HMACSigner(_KEY), HMACVerifier(_KEY), **kw)


def test_fail_closed_without_tpm():
    # Dispositivos inexistentes → attest() falla cerrado (no inventa medición).
    p = _provider(device_paths=("/nonexistent/tpmrm0", "/nonexistent/tpm0"))
    with pytest.raises(TpmUnavailableError):
        p.attest()


def test_implements_protocol():
    p = _provider(device_paths=("/nonexistent/tpm0",))
    assert isinstance(p, AttestationProvider)


def test_measurement_from_event_log(tmp_path):
    device = tmp_path / "tpmrm0"
    device.write_bytes(b"")            # "dispositivo" presente
    evlog = tmp_path / "evlog"
    evlog.write_bytes(b"measured-boot-bytes")
    p = _provider(device_paths=(str(device),), event_log_path=str(evlog))
    q = p.attest()
    expected = "evlog:" + hashlib.sha256(b"measured-boot-bytes").hexdigest()
    assert q.measurement == expected
    assert q.algo == "tpm-rooted"
    assert p.appraise(q, expected) is True


def test_measurement_presence_when_log_unreadable(tmp_path):
    device = tmp_path / "tpm0"
    device.write_bytes(b"")
    p = _provider(device_paths=(str(device),), event_log_path=str(tmp_path / "missing"))
    q = p.attest()
    assert q.measurement.startswith("tpm-present:")
    assert p.appraise(q, q.measurement) is True


def test_appraise_rejects_wrong_measurement(tmp_path):
    device = tmp_path / "tpm0"
    device.write_bytes(b"")
    p = _provider(device_paths=(str(device),), event_log_path=str(tmp_path / "missing"))
    q = p.attest()
    assert p.appraise(q, "evlog:deadbeef") is False


def test_appraise_rejects_bad_signature(tmp_path):
    device = tmp_path / "tpm0"
    device.write_bytes(b"")
    p = _provider(device_paths=(str(device),), event_log_path=str(tmp_path / "missing"))
    q = p.attest()
    forged = Quote(measurement=q.measurement, signature="00" * 32, algo=q.algo)
    assert p.appraise(forged, q.measurement) is False
