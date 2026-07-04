"""Tests para PreflightGate — el primer paso barato/determinista de autoauditoría.

Cubre: escaneo de CVEs vía pip-audit (mockeado, nunca real en test) + radar de
saneamiento (sanitation_audit.py real, read-only, rápido). Ver spec en la tarea
del roadmap "juicio real para autoauditoría".
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlas.core.self_maintenance.preflight_gate import PreflightGate, PreflightResult


def _fake_run_factory(stdout: str, returncode: int = 0, stderr: str = ""):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return _fake_run


def test_no_cves_passes(monkeypatch):
    payload = {
        "dependencies": [
            {"name": "requests", "version": "2.31.0", "vulns": []},
            {"name": "cryptography", "version": "49.0.0", "vulns": []},
        ],
        "fixes": [],
    }
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    gate = PreflightGate()
    result = gate.check()
    assert result.passed is True
    assert result.cve_found is False
    assert result.cve_findings == []


def test_cves_found_fails(monkeypatch):
    payload = {
        "dependencies": [
            {
                "name": "somepkg",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "CVE-2026-0001",
                        "fix_versions": ["1.0.1"],
                        "description": "algo malo",
                    }
                ],
            },
            {"name": "otherpkg", "version": "2.0.0", "vulns": []},
        ],
        "fixes": [],
    }
    # pip-audit devuelve returncode != 0 cuando SÍ encuentra vulnerabilidades
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=1),
    )
    gate = PreflightGate()
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    finding = result.cve_findings[0]
    assert "somepkg" in finding
    assert "1.0.0" in finding
    assert "CVE-2026-0001" in finding
    assert "1.0.1" in finding


def test_pip_audit_raises_fails_closed(monkeypatch):
    def _raise_run(*args, **kwargs):
        raise OSError("pip-audit no encontrado")

    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run", _raise_run
    )
    gate = PreflightGate()
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    assert "pip-audit no pudo ejecutarse" in result.cve_findings[0]


def test_pip_audit_non_json_stdout_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory("esto no es json", returncode=0, stderr="algo raro"),
    )
    gate = PreflightGate()
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    assert "no-JSON" in result.cve_findings[0] or "pip-audit no pudo ejecutarse" in result.cve_findings[0]


def test_sanitation_findings_has_four_keys(monkeypatch):
    payload = {"dependencies": [{"name": "requests", "version": "2.31.0", "vulns": []}], "fixes": []}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    gate = PreflightGate()
    result = gate.check()
    assert set(result.sanitation_findings.keys()) == {
        "vapor",
        "graveyard_overdue",
        "empty_dirs",
        "stale_refs",
    }
    for key, value in result.sanitation_findings.items():
        assert isinstance(value, list)


def test_sanitation_audit_load_failure_yields_error_key(monkeypatch):
    payload = {"dependencies": [], "fixes": []}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.importlib.util.spec_from_file_location",
        lambda *args, **kwargs: None,
    )
    gate = PreflightGate()
    result = gate.check()
    assert "error" in result.sanitation_findings
    assert isinstance(result.sanitation_findings["error"], list)
    assert len(result.sanitation_findings["error"]) == 1


def test_to_dict_roundtrip():
    result = PreflightResult(
        passed=False,
        cve_found=True,
        cve_findings=["pkg==1.0.0: CVE-2026-9999 (fix: 1.0.1)"],
        sanitation_findings={
            "vapor": ["a.py"],
            "graveyard_overdue": [],
            "empty_dirs": [],
            "stale_refs": ["README.md -> docs/x.md (no existe)"],
        },
    )
    d = result.to_dict()
    assert d == {
        "passed": False,
        "cve_found": True,
        "cve_findings": ["pkg==1.0.0: CVE-2026-9999 (fix: 1.0.1)"],
        "sanitation_findings": {
            "vapor": ["a.py"],
            "graveyard_overdue": [],
            "empty_dirs": [],
            "stale_refs": ["README.md -> docs/x.md (no existe)"],
        },
    }
