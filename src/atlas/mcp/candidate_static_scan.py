"""Etapa 2A (parte 3) de ADR-075 — análisis estático real (semgrep) del código
fuente extraído de un candidato ``stdio``.

``adopt-real-not-shell`` (ADR-075 I7): envuelve el binario real de
``semgrep`` (análisis ESTÁTICO -- parsea, no ejecuta el código), no un
cascarón reimplementado. Verificado en vivo contra un paquete real de PyPI
(``adeu``): encontró hallazgos reales (uso de ``xml`` vulnerable a XXE,
llamadas dinámicas a ``urllib``).

Semgrep NO ejecuta el código que analiza -- corre directo, sin BwrapJail
(eso es para la fase de EJECUCIÓN del server extraído, si se llega, aparte).
Runner de subproceso inyectable: sin invocar semgrep de verdad en tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from atlas.core.adversarial_panel import Severity


def _semgrep_binary() -> str:
    """'semgrep' plano depende del PATH del proceso que lanza el subproceso --
    fuera de un venv activado (ej. este módulo invocado con el intérprete
    absoluto del venv) no se resuelve aunque esté instalado ahí mismo. Se
    busca junto a ``sys.executable`` (mismo venv), con fallback al PATH."""
    candidate = Path(sys.executable).parent / "semgrep"
    return str(candidate) if candidate.is_file() else "semgrep"

# (cmd: list[str], cwd: str, timeout: float) -> (returncode, stdout, stderr)
SubprocessRunner = Callable[[list[str], str, float], tuple[int, str, str]]

_SEVERITY_MAP = {"ERROR": Severity.MAJOR, "WARNING": Severity.MINOR, "INFO": Severity.MINOR}


def _default_runner(cmd: list[str], cwd: str, timeout: float) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


@dataclass(frozen=True)
class StaticFinding:
    check_id: str
    path: str
    line: int
    severity: Severity
    message: str


@dataclass(frozen=True)
class StaticScanResult:
    ok: bool
    findings: list[StaticFinding] = field(default_factory=list)
    reason: str = ""

    @property
    def worst_severity(self) -> Severity:
        if not self.findings:
            return Severity.NONE
        return max(f.severity for f in self.findings)


def scan_source(
    source_dir: str,
    *,
    runner: SubprocessRunner = _default_runner,
    ruleset: str = "p/security-audit",
    timeout_seconds: float = 60.0,
) -> StaticScanResult:
    """Fail-closed (I6): un semgrep que crashea, se cuelga, o devuelve algo
    no parseable NUNCA se trata como "código limpio" -- ``ok=False`` corta el
    pipeline aquí, el candidato no se promociona.

    ``source_dir`` se resuelve a ABSOLUTO antes de construir el comando --
    se pasa como argumento Y como cwd del subproceso; si fuera relativo,
    tras el chdir del subproceso ya no apuntaría a donde apuntaba (bug real
    2026-07-24: semgrep devolvía "Invalid scanning root")."""
    abs_source_dir = str(Path(source_dir).resolve())
    cmd = [_semgrep_binary(), "--config", ruleset, "--json", "--quiet", abs_source_dir]
    try:
        returncode, stdout, stderr = runner(cmd, abs_source_dir, timeout_seconds)
    except TimeoutError:
        return StaticScanResult(ok=False, reason=f"semgrep excedió el timeout de {timeout_seconds}s")
    except Exception as exc:  # noqa: BLE001 — fail-closed ante cualquier fallo del runner
        return StaticScanResult(ok=False, reason=f"semgrep falló al ejecutar: {exc}")

    if returncode not in (0, 1):  # semgrep: 0=sin hallazgos, 1=con hallazgos, otro=error real
        return StaticScanResult(ok=False, reason=f"semgrep devolvió código {returncode}: {stderr[:200]}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return StaticScanResult(ok=False, reason="salida de semgrep no es JSON válido")

    findings = [
        StaticFinding(
            check_id=str(r.get("check_id", "")),
            path=str(r.get("path", "")),
            line=int((r.get("start") or {}).get("line", 0)),
            severity=_SEVERITY_MAP.get(str((r.get("extra") or {}).get("severity", "")), Severity.MINOR),
            message=str((r.get("extra") or {}).get("message", "")),
        )
        for r in data.get("results", [])
    ]
    return StaticScanResult(ok=True, findings=findings, reason="ok")
