"""Cumplimiento de la mesa de trabajo obligatoria (2026-07-23).

El operador pidió: aviso no bloqueante si no se consultó workbench://manifest
antes de trabajo sustancial, pero el hallazgo debe quedar REGISTRADO de forma
durable para que un ciclo de auditoría/coldupdate futuro lo revise -- no un
recordatorio que se pierde en el turno. Fail-soft: nunca debe poder romper el
hook de prompts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.mcp.workbench_compliance import check_and_record, is_stale, record_finding


def _write_consultation(path: Path, at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": at.isoformat()}) + "\n", encoding="utf-8")


def test_missing_log_is_stale(tmp_path: Path) -> None:
    assert is_stale(tmp_path / "nope.jsonl") is True


def test_recent_consultation_is_not_stale(tmp_path: Path) -> None:
    path = tmp_path / "consultations.jsonl"
    now = datetime.now(timezone.utc)
    _write_consultation(path, now - timedelta(minutes=1))
    assert is_stale(path, now=now) is False


def test_old_consultation_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "consultations.jsonl"
    now = datetime.now(timezone.utc)
    _write_consultation(path, now - timedelta(hours=2))
    assert is_stale(path, now=now, stale_after_seconds=1800) is True


def test_corrupt_log_treated_as_stale_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "consultations.jsonl"
    path.write_text("{not valid json", encoding="utf-8")
    assert is_stale(path) is True


def test_record_finding_hashes_prompt_never_plaintext(tmp_path: Path) -> None:
    findings = tmp_path / "findings.jsonl"
    record_finding(findings, prompt="secreto que nunca debe aparecer en claro")
    text = findings.read_text(encoding="utf-8")
    assert "secreto" not in text
    entry = json.loads(text.strip())
    assert "prompt_hash" in entry and "at" in entry
    assert entry["finding"] == "workbench_not_consulted"


def test_check_and_record_returns_none_when_fresh(tmp_path: Path) -> None:
    consultation_log = tmp_path / "consultations.jsonl"
    _write_consultation(consultation_log, datetime.now(timezone.utc))
    findings = tmp_path / "findings.jsonl"

    result = check_and_record(
        consultation_log_path=consultation_log, findings_path=findings, prompt="hola",
    )
    assert result is None
    assert not findings.exists()


def test_check_and_record_warns_and_persists_finding_when_stale(tmp_path: Path) -> None:
    consultation_log = tmp_path / "consultations.jsonl"  # no existe -> stale
    findings = tmp_path / "findings.jsonl"

    result = check_and_record(
        consultation_log_path=consultation_log, findings_path=findings, prompt="hola",
    )
    assert result is not None and "workbench" in result.lower()
    assert findings.is_file()


def test_check_and_record_never_raises_on_unwritable_findings_path(tmp_path: Path) -> None:
    """Fail-soft real: si findings_path no se puede escribir (p.ej. un
    directorio con ese nombre), el hook NUNCA debe romperse por esto."""
    bad_findings = tmp_path  # es un directorio, no se puede abrir como fichero
    result = check_and_record(
        consultation_log_path=tmp_path / "nope.jsonl", findings_path=bad_findings, prompt="x",
    )
    assert result is None  # se traga el error, no revienta el hook
