"""Tests de `Orchestrator.security_council_unblock` (ADR-077.3) -- comando
HITL explícito para revocar un rechazo permanente que resulte falso
positivo. Objeción del Cónclave real: el diseño original no tenía ninguna
vía de apelación para un rechazo permanente equivocado."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.adversarial_panel import Severity
from atlas.core.decider.security_council_gate import SecurityReport
from atlas.core.decider.security_council_registry import is_rejected, record_rejection
from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "atlas").mkdir(parents=True)
    (tmp_path / "core").mkdir(parents=True)
    return Orchestrator(workspace=tmp_path / "atlas")


def _registry_path(orch: Orchestrator) -> Path:
    return orch._project_root() / "workspace" / "security_council" / "rejected.jsonl"


def test_unblock_nonexistent_hash_reports_not_found(orch: Orchestrator) -> None:
    result = orch.security_council_unblock("nunca-rechazado", reason="x", actor="operador")
    assert result["status"] == "not_found"


def test_unblock_real_rejection_clears_it(orch: Orchestrator) -> None:
    path = _registry_path(orch)
    report = SecurityReport(severity=Severity.MAJOR, triggered_by="x", recommended_action="y")
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", report, path)
    assert is_rejected("abc123", path) is True

    result = orch.security_council_unblock("abc123", reason="falso positivo confirmado", actor="operador")
    assert result["status"] == "unblocked"
    assert is_rejected("abc123", path) is False


def test_unblock_logs_to_merkle(orch: Orchestrator) -> None:
    path = _registry_path(orch)
    report = SecurityReport(severity=Severity.MAJOR, triggered_by="x", recommended_action="y")
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", report, path)

    orch.security_council_unblock("abc123", reason="falso positivo", actor="operador")

    entries = [e for e in orch._merkle.tail(50) if e.action == "security_council.unblock"]
    assert len(entries) == 1
    assert entries[0].payload["action_hash"] == "abc123"
    assert entries[0].payload["actor"] == "operador"
