"""OSM-031 log-native: LogBehavioralAuditor detecta mismo-input→output-distinto."""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas.security.authorization import Ed25519Signer
from atlas.security.log_behavioral import (
    CovertChangeFinding,
    LogBehavioralAuditor,
    audit_entries,
)
from atlas.transparency.client_cosign import InspectionRecord, OutputInspectionRecord
from atlas.transparency.log import TransparencyLog


def _signer() -> Ed25519Signer:
    return Ed25519Signer(Ed25519PrivateKey.generate().private_bytes_raw())


def _in(seq: int, payload_hash: str) -> bytes:
    return InspectionRecord(
        seq=seq, payload_hash=payload_hash, cosig="{}", decision="allow",
        cause="gateway.auto", timestamp_ns=seq,
    ).to_bytes()


def _out(seq: int, output_hash: str) -> bytes:
    return OutputInspectionRecord(
        seq=seq, output_hash=output_hash, decision="allow", cause="gateway.auto",
        timestamp_ns=seq,
    ).to_bytes()


def test_same_input_different_output_flagged():
    # input "A" en seq 0 → out X; mismo input "A" en seq 2 → out Y (cambio).
    entries = [_in(0, "A"), _out(0, "X"), _in(2, "A"), _out(2, "Y")]
    findings = audit_entries(entries)
    assert len(findings) == 1
    f = findings[0]
    assert f.input_hash == "A"
    assert set(f.output_hashes) == {"X", "Y"}
    assert f.seqs == (0, 2)


def test_same_input_same_output_no_finding():
    entries = [_in(0, "A"), _out(0, "X"), _in(1, "A"), _out(1, "X")]
    assert audit_entries(entries) == []


def test_different_inputs_no_finding():
    entries = [_in(0, "A"), _out(0, "X"), _in(1, "B"), _out(1, "Y")]
    assert audit_entries(entries) == []


def test_unique_input_no_signal():
    # input visto una sola vez → sin señal (cobertura, no garantía).
    entries = [_in(0, "A"), _out(0, "X")]
    assert audit_entries(entries) == []


def test_malformed_and_orphan_entries_ignored():
    # leaf basura + un output sin su input no rompen ni generan falso hallazgo.
    entries = [b"{not json", _out(9, "Z"), _in(0, "A"), _out(0, "X")]
    assert audit_entries(entries) == []


def test_auditor_over_real_log():
    log = TransparencyLog(_signer())
    for e in [_in(0, "A"), _out(0, "X"), _in(5, "A"), _out(5, "W")]:
        log.append(e)
    findings = LogBehavioralAuditor(log).audit()
    assert len(findings) == 1
    assert findings[0].input_hash == "A"
    assert set(findings[0].output_hashes) == {"X", "W"}


def test_three_distinct_outputs():
    entries = [
        _in(0, "A"), _out(0, "X"),
        _in(1, "A"), _out(1, "Y"),
        _in(2, "A"), _out(2, "Z"),
    ]
    f = audit_entries(entries)[0]
    assert f.output_hashes == ("X", "Y", "Z")  # orden de primera aparición
    assert isinstance(f, CovertChangeFinding)
