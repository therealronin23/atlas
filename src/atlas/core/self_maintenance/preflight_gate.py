"""PreflightGate — el primer paso, más barato y determinista, de autoauditoría.

Antes de gastar ningún LLM en juicio real de una autoauditoría, se descarta
gratis lo obviamente malo: CVEs de dependencias (pip-audit) + radar de
arquitectura/conexión (scripts/sanitation_audit.py). Fail-closed: cualquier
fallo del escaneo de CVEs (no del hallazgo de vulnerabilidades en sí, sino de
la ejecución del escaneo) se trata como "no pasa" — nunca se asume "sin CVEs"
por defecto ante una duda.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class PreflightResult:
    passed: bool
    cve_found: bool
    cve_findings: list[str]
    sanitation_findings: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "cve_found": self.cve_found,
            "cve_findings": list(self.cve_findings),
            "sanitation_findings": dict(self.sanitation_findings),
        }


class PreflightGate:
    def __init__(self, *, python_executable: str | None = None) -> None:
        self._python = python_executable or sys.executable

    def check(self) -> PreflightResult:
        cve_found, cve_findings = self._scan_cves()
        sanitation_findings = self._run_sanitation()
        return PreflightResult(
            passed=not cve_found,
            cve_found=cve_found,
            cve_findings=cve_findings,
            sanitation_findings=sanitation_findings,
        )

    def _scan_cves(self) -> tuple[bool, list[str]]:
        try:
            result = subprocess.run(
                [self._python, "-m", "pip_audit", "--format", "json"],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return True, [f"pip-audit no pudo ejecutarse: {exc}"]
        # pip-audit devuelve returncode!=0 cuando SÍ encuentra vulnerabilidades
        # (ese es el comportamiento esperado, no un fallo del escaneo) — no
        # tratar returncode!=0 como fallo de ejecución; solo un stdout no-JSON
        # o una excepción real cuentan como "el escaneo no corrió".
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return True, [f"pip-audit no pudo ejecutarse: salida no-JSON ({exc}); stderr: {result.stderr[:300]}"]
        findings: list[str] = []
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []) or []:
                fixes = ",".join(vuln.get("fix_versions", []) or []) or "sin fix conocido"
                findings.append(
                    f"{dep.get('name')}=={dep.get('version')}: {vuln.get('id')} (fix: {fixes})"
                )
        return bool(findings), findings

    def _run_sanitation(self) -> dict[str, list[str]]:
        try:
            spec = importlib.util.spec_from_file_location(
                "sanitation_audit", _REPO_ROOT / "scripts" / "sanitation_audit.py"
            )
            if spec is None or spec.loader is None:
                raise ImportError("no se pudo cargar scripts/sanitation_audit.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return {
                "vapor": module.vapor_audit(),
                "classified_zero_importers": module.classified_zero_importers(),
                "graveyard_overdue": module.graveyard_overdue(),
                "empty_dirs": module.empty_dirs(),
                "stale_refs": module.stale_refs(),
            }
        except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
            return {"error": [f"sanitation_audit no pudo ejecutarse: {exc}"]}
