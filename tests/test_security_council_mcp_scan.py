"""Tests de `mcp_vetting_scan_fn` -- corrige un hueco real encontrado al
revisar la implementación de ADR-077: el gate genérico (`default_scan_fn`)
solo mira `action.descriptor`, que para `mcp_adopt` es el nombre bare del
candidato (ej. "ai.adeu/adeu") -- NO la evidencia real de vetting (semgrep,
`worst_severity`) que ADR-075 ya calculó y persistió en
`docs/design/mcp_catalog_stage2_report.jsonl`.

Corrección explícita del operador (2026-07-24): "cortar los reintentos de
adeu como si fuera lo único que existe me parece super mal... es posible
que se repita en el futuro y no tiene por qué ser adeu". Este scanner
consulta la evidencia REAL por nombre de candidato -- cualquier candidato
futuro con un hallazgo MAJOR/BLOCKING real queda cubierto estructuralmente,
no solo el caso que motivó el hallazgo.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.decider.security_council_mcp_scan import mcp_vetting_scan_fn


def _write_report(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_major_finding_is_dirty(tmp_path: Path) -> None:
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "stdio", "name": "ai.adeu/adeu", "completed": True,
         "stage_reached": "static_scan", "reason": "ok", "worst_severity": "MAJOR"},
    ])
    scan = mcp_vetting_scan_fn(report)
    result = scan("ai.adeu/adeu")
    assert result.clean is False
    assert "MAJOR" in result.detail


def test_blocking_finding_is_dirty(tmp_path: Path) -> None:
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "stdio", "name": "some.other/candidate", "completed": True,
         "stage_reached": "static_scan", "reason": "ok", "worst_severity": "BLOCKING"},
    ])
    scan = mcp_vetting_scan_fn(report)
    result = scan("some.other/candidate")
    assert result.clean is False


def test_clean_stdio_candidate_is_clean(tmp_path: Path) -> None:
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "stdio", "name": "good.package/mcp", "completed": True,
         "stage_reached": "static_scan", "reason": "ok", "worst_severity": "NONE"},
    ])
    scan = mcp_vetting_scan_fn(report)
    assert scan("good.package/mcp").clean is True


def test_incomplete_vetting_is_dirty_fail_closed(tmp_path: Path) -> None:
    """No completó stage2 (terminal o retryable) -- no confirmado limpio,
    nunca se asume clean por defecto (I6)."""
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "stdio", "name": "unknown.status/mcp", "completed": False,
         "stage_reached": "lookup", "reason": "registryType no soportado: 'oci'"},
    ])
    scan = mcp_vetting_scan_fn(report)
    result = scan("unknown.status/mcp")
    assert result.clean is False


def test_candidate_not_in_report_is_dirty_fail_closed(tmp_path: Path) -> None:
    """Un candidato nunca vetado no se trata como limpio por omisión --
    exactamente el escenario 'no tiene por qué ser adeu': cualquier
    candidato futuro sin evidencia real cae aquí, no solo uno con nombre
    conocido."""
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "stdio", "name": "otro/candidato", "completed": True,
         "worst_severity": "NONE"},
    ])
    scan = mcp_vetting_scan_fn(report)
    result = scan("jamas.vetado/mcp")
    assert result.clean is False
    assert "sin vetting" in result.detail.lower() or "no vetado" in result.detail.lower()


def test_missing_report_file_is_dirty_fail_closed(tmp_path: Path) -> None:
    scan = mcp_vetting_scan_fn(tmp_path / "no_existe.jsonl")
    result = scan("cualquiera/candidato")
    assert result.clean is False


def test_completed_http_candidate_without_static_findings_is_clean(tmp_path: Path) -> None:
    """Pista http (I2-R): sin fuente que analizar por diseño -- completed=True
    (handshake real respondió) es la señal máxima disponible, se trata como
    limpio a este nivel (el criterio final de auto-adopción para http sigue
    bloqueado por ADR-076 C, esto solo decide si PASA este scanner)."""
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "http", "name": "remote.server/mcp", "completed": True,
         "reason": "ok", "tool_count": 5},
    ])
    scan = mcp_vetting_scan_fn(report)
    assert scan("remote.server/mcp").clean is True


def test_failed_http_candidate_is_dirty(tmp_path: Path) -> None:
    report = tmp_path / "report.jsonl"
    _write_report(report, [
        {"track": "http", "name": "dead.server/mcp", "completed": False,
         "reason": "HTTP 401 del endpoint remoto", "tool_count": 0},
    ])
    scan = mcp_vetting_scan_fn(report)
    assert scan("dead.server/mcp").clean is False
