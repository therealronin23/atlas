"""CLI tests for atlas self-audit commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


class _FakeSelfAudit:
    def run(self, **kwargs):
        class Report:
            def to_dict(self):
                return {"status": "completed", "kwargs": kwargs, "cycles": []}

        return Report()

    def status(self):
        return {"stop_requested": False, "latest_report": None}

    def proposals(self):
        return [{"id": "candidate-x", "status": "dry_run"}]

    def latest_report(self):
        return {"id": "self-audit-test", "status": "completed"}

    def stop(self):
        self.stopped = True


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.runner = _FakeSelfAudit()

    def self_audit(self):
        return self.runner


def test_self_audit_run_cli(monkeypatch) -> None:
    fake = _FakeOrchestrator()
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(
        cli_mod.cli,
        ["self-audit", "run", "--hours", "1", "--max-cycles", "1", "--dry-run"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "completed"
    assert payload["kwargs"]["dry_run"] is True


def test_self_audit_inspection_commands(monkeypatch) -> None:
    fake = _FakeOrchestrator()
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)
    runner = CliRunner()

    for args in (
        ["self-audit", "status"],
        ["self-audit", "proposals"],
        ["self-audit", "report"],
        ["self-audit", "stop"],
    ):
        result = runner.invoke(cli_mod.cli, args)
        assert result.exit_code == 0
