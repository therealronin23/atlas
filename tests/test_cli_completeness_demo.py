"""CLI smoke tests for the subject-enforced completeness demo."""

from __future__ import annotations

import json

from click.testing import CliRunner

from atlas.interfaces.cli import cli


def test_completeness_demo_json_reports_all_scenarios_ok() -> None:
    result = CliRunner().invoke(cli, ["completeness-demo", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "ok"
    assert report["scenarios"]
    assert all(report["scenarios"].values())


def test_completeness_demo_human_output_reports_status_ok() -> None:
    result = CliRunner().invoke(cli, ["completeness-demo"])
    assert result.exit_code == 0, result.output
    assert "Subject-Enforced Completeness Demo" in result.output
    assert "Status:" in result.output
