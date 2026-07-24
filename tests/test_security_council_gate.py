"""Tests de `security_council_gate` (ADR-077.1) -- gate de seguridad de dos
etapas (escaneo automatizado + auditor LLM único), delante del Decider
existente. Fail-closed explícito: un fallo en CUALQUIER etapa produce
`flagged`, nunca `clean` -- objeción BLOCKING del Cónclave real que revisó
este diseño (2026-07-24), incorporada aquí antes de escribir una sola línea
de producción.
"""

from __future__ import annotations

from atlas.core.adversarial_panel import Severity
from atlas.core.decider.security_council_gate import (
    AuditFinding,
    ScanFinding,
    run_security_council_gate,
)


def _clean_scan(descriptor: str) -> ScanFinding:
    return ScanFinding(clean=True, detail="ok")


def _clean_audit(descriptor: str) -> AuditFinding:
    return AuditFinding(clean=True, detail="ok")


def test_clean_when_both_scan_and_audit_pass() -> None:
    verdict = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=_clean_audit)
    assert verdict.status == "clean"
    assert verdict.report is None


def test_flagged_when_scan_flags() -> None:
    def dirty_scan(descriptor: str) -> ScanFinding:
        return ScanFinding(clean=False, detail="patrón peligroso encontrado")

    verdict = run_security_council_gate("x", scan_fn=dirty_scan, audit_fn=_clean_audit)
    assert verdict.status == "flagged"
    assert verdict.report is not None
    assert "patrón peligroso" in verdict.report.triggered_by


def test_scan_flag_severity_is_blocking_deterministic_evidence() -> None:
    """Hallazgo de auditoría de seguridad (2026-07-24): un hit de escaneo
    (IOC-regex/evidencia real de vetting) es determinista -- distinto de
    'el LLM tuvo una corazonada'. Debe pesar más en la severidad."""
    def dirty_scan(descriptor: str) -> ScanFinding:
        return ScanFinding(clean=False, detail="x")

    verdict = run_security_council_gate("x", scan_fn=dirty_scan, audit_fn=_clean_audit)
    assert verdict.report.severity == Severity.BLOCKING


def test_audit_flag_severity_stays_major_probabilistic_evidence() -> None:
    """El auditor LLM único es una sola voz, probabilística -- se queda en
    MAJOR (más débil que un hit determinista de escaneo), no BLOCKING."""
    def dirty_audit(descriptor: str) -> AuditFinding:
        return AuditFinding(clean=False, detail="x")

    verdict = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=dirty_audit)
    assert verdict.report.severity == Severity.MAJOR


def test_flagged_when_audit_flags() -> None:
    def dirty_audit(descriptor: str) -> AuditFinding:
        return AuditFinding(clean=False, detail="riesgo semántico detectado")

    verdict = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=dirty_audit)
    assert verdict.status == "flagged"
    assert "riesgo semántico" in verdict.report.triggered_by


def test_scan_flag_short_circuits_before_calling_audit() -> None:
    """Si el escaneo ya marca algo, no hace falta pagar la llamada LLM."""
    called = {"audit": False}

    def dirty_scan(descriptor: str) -> ScanFinding:
        return ScanFinding(clean=False, detail="x")

    def audit_that_should_not_run(descriptor: str) -> AuditFinding:
        called["audit"] = True
        return AuditFinding(clean=True)

    run_security_council_gate("x", scan_fn=dirty_scan, audit_fn=audit_that_should_not_run)
    assert called["audit"] is False


def test_scan_exception_is_flagged_not_clean_fail_closed() -> None:
    def crashing_scan(descriptor: str) -> ScanFinding:
        raise RuntimeError("proveedor de escaneo caído")

    verdict = run_security_council_gate("x", scan_fn=crashing_scan, audit_fn=_clean_audit)
    assert verdict.status == "flagged"
    assert verdict.report.severity in (Severity.MAJOR, Severity.BLOCKING)
    assert "escaneo" in verdict.report.triggered_by.lower()


def test_audit_exception_is_flagged_not_clean_fail_closed() -> None:
    def crashing_audit(descriptor: str) -> AuditFinding:
        raise TimeoutError("proveedor LLM sin respuesta")

    verdict = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=crashing_audit)
    assert verdict.status == "flagged"
    assert "auditor" in verdict.report.triggered_by.lower()


def test_checks_run_tracks_what_actually_executed() -> None:
    verdict = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=_clean_audit)
    assert verdict.status == "clean"

    def dirty_audit(descriptor: str) -> AuditFinding:
        return AuditFinding(clean=False, detail="x")

    flagged = run_security_council_gate("x", scan_fn=_clean_scan, audit_fn=dirty_audit)
    assert "scan" in flagged.report.checks_run
    assert "llm_audit" in flagged.report.checks_run
