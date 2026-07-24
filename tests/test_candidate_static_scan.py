"""
TDD — candidate_static_scan: etapa 2A (parte 3) de ADR-075.

Wrapper de ``semgrep`` real (adopt-real-not-shell, ADR-075 I7) sobre el
código fuente extraído de un candidato ``stdio``. Semgrep hace análisis
ESTÁTICO (parsea, no ejecuta) -- corre directo, sin BwrapJail (la ejecución
real del server extraído, si se llega a esa fase, sí lo necesita, ver
etapa 3 aparte). Runner de subproceso inyectable -- sin invocar el semgrep
real en tests unitarios (rápido, hermético; la prueba contra semgrep de
verdad ya se hizo en vivo contra un paquete real, ver commit).
"""

from __future__ import annotations

import json


def _fake_runner(returncode: int, stdout: str):
    def run(cmd, cwd, timeout):
        return returncode, stdout, ""
    return run


def test_scan_source_parses_findings_by_severity() -> None:
    from atlas.mcp.candidate_static_scan import scan_source
    from atlas.core.adversarial_panel import Severity

    semgrep_json = json.dumps({
        "results": [
            {"check_id": "python.lang.security.use-defused-xml", "path": "x/xml_debug.py",
             "start": {"line": 3}, "extra": {"severity": "ERROR", "message": "XXE risk"}},
            {"check_id": "python.lang.security.dynamic-urllib", "path": "x/tools/auth.py",
             "start": {"line": 38}, "extra": {"severity": "WARNING", "message": "dynamic urllib"}},
        ],
        "errors": [],
    })
    result = scan_source("/fake/dir", runner=_fake_runner(0, semgrep_json))
    assert result.ok is True
    assert len(result.findings) == 2
    assert result.findings[0].severity == Severity.MAJOR   # ERROR -> MAJOR
    assert result.findings[1].severity == Severity.MINOR   # WARNING -> MINOR
    assert result.worst_severity == Severity.MAJOR


def test_scan_source_clean_when_no_findings() -> None:
    from atlas.mcp.candidate_static_scan import scan_source
    from atlas.core.adversarial_panel import Severity

    result = scan_source("/fake/dir", runner=_fake_runner(0, json.dumps({"results": [], "errors": []})))
    assert result.ok is True
    assert result.findings == []
    assert result.worst_severity == Severity.NONE


def test_scan_source_failclosed_on_semgrep_crash() -> None:
    """Semgrep que crashea (returncode != 0/1) no se trata como "limpio" --
    fail-closed (I6): si no se pudo analizar, no se promociona."""
    from atlas.mcp.candidate_static_scan import scan_source

    result = scan_source("/fake/dir", runner=_fake_runner(2, "internal error"))
    assert result.ok is False
    assert "semgrep" in result.reason.lower()


def test_scan_source_failclosed_on_unparseable_output() -> None:
    from atlas.mcp.candidate_static_scan import scan_source

    result = scan_source("/fake/dir", runner=_fake_runner(0, "not json at all"))
    assert result.ok is False


def test_semgrep_cmd_resolves_binary_next_to_current_interpreter() -> None:
    """Fix real (2026-07-24): invocar 'semgrep' plano depende del PATH del
    shell que lanza el proceso -- fuera de un venv activado (ej. un script
    invocado con el intérprete absoluto del venv) 'semgrep' no se encuentra
    aunque esté instalado ahí mismo. Se resuelve junto a sys.executable."""
    import sys
    from pathlib import Path
    from atlas.mcp.candidate_static_scan import _semgrep_binary

    resolved = _semgrep_binary()
    assert resolved == str(Path(sys.executable).parent / "semgrep")


def test_scan_source_timeout_is_failclosed() -> None:
    from atlas.mcp.candidate_static_scan import scan_source

    def timeout_runner(cmd, cwd, timeout):
        raise TimeoutError("semgrep excedió el timeout")

    result = scan_source("/fake/dir", runner=timeout_runner)
    assert result.ok is False
    assert "timeout" in result.reason.lower()
