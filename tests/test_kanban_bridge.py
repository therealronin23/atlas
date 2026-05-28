"""ADR-028 — Twin Kanban Bridge tests (no live VPS, injected runner)."""

from __future__ import annotations

import subprocess

import pytest

from atlas.hermes.kanban_bridge import (
    DEFAULT_KANBAN_BIN,
    DEFAULT_SSH_HOST,
    KanbanBridge,
    KanbanResult,
)


class FakeRunner:
    """Records argv it was called with and returns a scripted result."""

    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = "", raises: Exception | None = None):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr
        self.raises = raises
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        if self.raises is not None:
            raise self.raises
        return self.rc, self.stdout, self.stderr


class FakeMerkle:
    def __init__(self):
        self.records: list[dict] = []

    def log(self, action, agent, result, risk_level="safe", payload=None, task_id=None):
        self.records.append(
            {"action": action, "agent": agent, "result": result, "risk_level": risk_level, "payload": payload or {}}
        )


# ---------------------------------------------------------------------------
# Argv construction
# ---------------------------------------------------------------------------


def test_run_builds_ssh_argv_with_defaults():
    runner = FakeRunner(stdout="ok")
    bridge = KanbanBridge(runner=runner)
    bridge.run("boards")
    argv = runner.calls[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert DEFAULT_SSH_HOST in argv
    # the remote command is the last arg, shell-quoted
    assert argv[-1] == f"{DEFAULT_KANBAN_BIN} kanban boards"


def test_run_quotes_arguments_with_spaces():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.create_task("hola mundo", body="cuerpo con espacios")
    remote = runner.calls[0][-1]
    # title with spaces must be quoted so the remote shell keeps it as one token
    assert "'hola mundo'" in remote
    assert "'cuerpo con espacios'" in remote


def test_custom_host_and_bin():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, ssh_host="root@10.0.0.1", kanban_bin="/opt/hermes")
    bridge.run("stats")
    argv = runner.calls[0]
    assert "root@10.0.0.1" in argv
    assert argv[-1] == "/opt/hermes kanban stats"


def test_host_from_env(monkeypatch):
    monkeypatch.setenv("HERMES_SSH_HOST", "root@env-host")
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.run("boards")
    assert "root@env-host" in runner.calls[0]


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------


def test_run_returns_ok_on_zero_exit():
    bridge = KanbanBridge(runner=FakeRunner(rc=0, stdout="done"))
    res = bridge.run("list")
    assert isinstance(res, KanbanResult)
    assert res.ok is True
    assert res.returncode == 0
    assert res.stdout == "done"


def test_run_returns_not_ok_on_nonzero_exit():
    bridge = KanbanBridge(runner=FakeRunner(rc=2, stderr="boom"))
    res = bridge.run("show", "T-1")
    assert res.ok is False
    assert res.returncode == 2
    assert res.stderr == "boom"


def test_json_stdout_is_parsed():
    bridge = KanbanBridge(runner=FakeRunner(stdout='[{"id": "T-1", "status": "ready"}]'))
    res = bridge.run("list")
    assert res.parsed == [{"id": "T-1", "status": "ready"}]


def test_non_json_stdout_parsed_none():
    bridge = KanbanBridge(runner=FakeRunner(stdout="plain text table"))
    res = bridge.run("list")
    assert res.parsed is None


# ---------------------------------------------------------------------------
# Typed wrappers
# ---------------------------------------------------------------------------


def test_create_task_flags():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.create_task("title", body="b", assignee="hermes", triage=True)
    remote = runner.calls[0][-1]
    assert "kanban create title --json" in remote
    assert "--body b" in remote
    assert "--assignee hermes" in remote
    assert "--triage" in remote
    # title is positional — there is no --title flag
    assert "--title" not in remote


def test_comment_positional_text():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.comment("T-1", "looks good", author="atlas")
    remote = runner.calls[0][-1]
    assert remote.endswith("kanban comment T-1 'looks good' --author atlas")
    assert "--text" not in remote


def test_complete_with_result():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.complete("T-1", result="done")
    remote = runner.calls[0][-1]
    assert remote.endswith("kanban complete T-1 --result done")


def test_list_tasks_status_filter():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner)
    bridge.list_tasks(status="ready")
    assert runner.calls[0][-1].endswith("kanban list --status ready")


def test_reachable_true_on_success():
    bridge = KanbanBridge(runner=FakeRunner(rc=0))
    assert bridge.reachable() is True


def test_reachable_false_on_transport_error():
    bridge = KanbanBridge(runner=FakeRunner(raises=FileNotFoundError("no ssh")))
    assert bridge.reachable() is False


# ---------------------------------------------------------------------------
# Merkle logging (rule 1)
# ---------------------------------------------------------------------------


def test_success_logged_to_merkle():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(rc=0))
    bridge.run("boards")
    assert len(merkle.records) == 1
    rec = merkle.records[0]
    assert rec["action"] == "kanban.boards"
    assert rec["agent"] == "kanban_bridge"
    assert rec["result"] == "success"


def test_failure_logged_to_merkle():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(rc=1))
    bridge.run("complete", "T-9")
    assert merkle.records[0]["result"] == "failure"


def test_transport_error_logged_and_raised():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(raises=subprocess.TimeoutExpired("ssh", 5)))
    with pytest.raises(subprocess.TimeoutExpired):
        bridge.run("list")
    assert merkle.records[0]["result"] == "failure"


def test_no_merkle_is_safe():
    bridge = KanbanBridge(merkle=None, runner=FakeRunner(rc=0))
    res = bridge.run("boards")  # must not raise
    assert res.ok is True
