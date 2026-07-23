"""CLI tests for `atlas selfbuild pause|resume|status` (t1-daemon-control-surface).

Superficie de control operativo del self-build daemon: sin esto, la única
forma de detenerlo era matar todo `atlas serve` (dashboard/API/MCP incluidos).
Los comandos operan directamente sobre el fichero de estado de
self_build_pause.py bajo ATLAS_CORE_ROOT -- no requieren un Orchestrator vivo.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


def test_status_reports_not_paused_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

    result = CliRunner().invoke(cli_mod.cli, ["selfbuild", "status"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"paused": False, "paused_at": None, "reason": None}


def test_pause_then_status_reports_paused_with_reason(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    runner = CliRunner()

    pause_result = runner.invoke(
        cli_mod.cli, ["selfbuild", "pause", "--reason", "sesion de desarrollo"],
    )
    assert pause_result.exit_code == 0

    status_result = runner.invoke(cli_mod.cli, ["selfbuild", "status"])
    payload = json.loads(status_result.output)
    assert payload["paused"] is True
    assert payload["reason"] == "sesion de desarrollo"

    state_file = tmp_path / "workspace" / "self_build" / "pause_state.json"
    assert state_file.is_file()


def test_resume_clears_pause(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    runner = CliRunner()

    runner.invoke(cli_mod.cli, ["selfbuild", "pause"])
    resume_result = runner.invoke(cli_mod.cli, ["selfbuild", "resume"])
    assert resume_result.exit_code == 0

    status_result = runner.invoke(cli_mod.cli, ["selfbuild", "status"])
    assert json.loads(status_result.output)["paused"] is False
