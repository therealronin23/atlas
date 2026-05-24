"""Gate G tests for CLI approval persistence."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

import atlas.governance.governance_l0 as governance_l0
from atlas.interfaces import cli as cli_module
from atlas.interfaces.cli import cli


def _reset_cli() -> None:
    cli_module._orch = None
    governance_l0.GovernanceL0._instance = None


def test_cli_pending_and_approve_survive_new_orchestrator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "atlas"
    monkeypatch.setenv("ATLAS_HOME", str(workspace))
    runner = CliRunner()

    _reset_cli()
    submitted = runner.invoke(
        cli,
        ["task", "editor write projects/cli_gate_g.txt :: hello from cli"],
    )
    assert submitted.exit_code == 0, submitted.output
    assert "AWAITING_APPROVAL" in submitted.output

    _reset_cli()
    pending = runner.invoke(cli, ["pending"])
    assert pending.exit_code == 0, pending.output
    assert "editor.write" in pending.output

    task_id = next((workspace / "memory" / "pending_approvals").glob("*.json")).stem

    _reset_cli()
    approved = runner.invoke(cli, ["approve", task_id])
    assert approved.exit_code == 0, approved.output
    assert "done" in approved.output
    assert (workspace / "projects" / "cli_gate_g.txt").read_text() == "hello from cli"

    _reset_cli()
    empty = runner.invoke(cli, ["pending"])
    assert empty.exit_code == 0, empty.output
    assert "Sin approvals pendientes" in empty.output

    governance_l0.GovernanceL0._instance = None
