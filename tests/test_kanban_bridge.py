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


SSH_HOST = "root@100.64.0.2"


@pytest.fixture(autouse=True)
def configured_ssh_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_SSH_HOST", SSH_HOST)


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
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.run("boards")
    argv = runner.calls[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert DEFAULT_SSH_HOST == ""
    assert SSH_HOST in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    # The SSH login may be root, but the process is always demoted to the
    # dedicated service account with its explicit HOME/HERMES_HOME.
    assert argv[-1] == (
        "runuser -u hermes -- env HOME=/var/lib/hermes "
        "HERMES_HOME=/var/lib/hermes/.hermes "
        f"{DEFAULT_KANBAN_BIN} kanban boards"
    )


def test_ssh_transport_requires_an_explicit_destination(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HERMES_SSH_HOST", raising=False)
    with pytest.raises(ValueError, match="HERMES_SSH_HOST"):
        KanbanBridge(runner=FakeRunner(), transport="ssh")


@pytest.mark.parametrize(
    "host",
    [
        "-oProxyCommand=evil",
        "root@host name",
        "root@",
        "root@178.105.216.187",
        "root@example.com",
    ],
)
def test_unsafe_ssh_destinations_are_rejected(host: str):
    with pytest.raises(ValueError, match="SSH destination"):
        KanbanBridge(runner=FakeRunner(), ssh_host=host, transport="ssh")


def test_unknown_transport_is_rejected():
    with pytest.raises(ValueError, match="transport"):
        KanbanBridge(runner=FakeRunner(), transport="magic")


def test_run_quotes_arguments_with_spaces():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.create_task("hola mundo", body="cuerpo con espacios")
    remote = runner.calls[0][-1]
    # title with spaces must be quoted so the remote shell keeps it as one token
    assert "'hola mundo'" in remote
    assert "'cuerpo con espacios'" in remote


def test_custom_host_and_bin():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, ssh_host="root@10.0.0.1", kanban_bin="/opt/hermes", transport="ssh")
    bridge.run("stats")
    argv = runner.calls[0]
    assert "root@10.0.0.1" in argv
    assert argv[-1].endswith("/opt/hermes kanban stats")
    assert argv[-1].startswith("runuser -u hermes -- env ")


def test_host_from_env(monkeypatch):
    monkeypatch.setenv("HERMES_SSH_HOST", "root@hermes.example-tailnet.ts.net")
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.run("boards")
    assert "root@hermes.example-tailnet.ts.net" in runner.calls[0]


def test_transport_local_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "local")
    monkeypatch.setenv("HERMES_KANBAN_BOARD_PATH", str(tmp_path / "board.json"))
    monkeypatch.setenv("HERMES_KANBAN_LOCAL_BIN", "/definitely-missing-hermes")
    bridge = KanbanBridge()
    res = bridge.run("boards")
    assert res.ok is True
    assert res.parsed == [{"id": "local", "name": "local-hermes", "transport": "local"}]


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------


def test_run_returns_ok_on_zero_exit():
    bridge = KanbanBridge(runner=FakeRunner(rc=0, stdout="done"), transport="ssh")
    res = bridge.run("list")
    assert isinstance(res, KanbanResult)
    assert res.ok is True
    assert res.returncode == 0
    assert res.stdout == "done"


def test_run_returns_not_ok_on_nonzero_exit():
    bridge = KanbanBridge(runner=FakeRunner(rc=2, stderr="boom"), transport="ssh")
    res = bridge.run("show", "T-1")
    assert res.ok is False
    assert res.returncode == 2
    assert res.stderr == "boom"


def test_unsupported_kanban_action_is_rejected_before_ssh():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
    with pytest.raises(ValueError, match="unsupported kanban action"):
        bridge.run("plugin", "install", "untrusted")
    assert runner.calls == []


def test_json_stdout_is_parsed():
    bridge = KanbanBridge(runner=FakeRunner(stdout='[{"id": "T-1", "status": "ready"}]'), transport="ssh")
    res = bridge.run("list")
    assert res.parsed == [{"id": "T-1", "status": "ready"}]


def test_non_json_stdout_parsed_none():
    bridge = KanbanBridge(runner=FakeRunner(stdout="plain text table"), transport="ssh")
    res = bridge.run("list")
    assert res.parsed is None


# ---------------------------------------------------------------------------
# Typed wrappers
# ---------------------------------------------------------------------------


def test_create_task_flags():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
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
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.comment("T-1", "looks good", author="atlas")
    remote = runner.calls[0][-1]
    assert remote.endswith("kanban comment T-1 'looks good' --author atlas")
    assert "--text" not in remote


def test_complete_with_result():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.complete("T-1", result="done")
    remote = runner.calls[0][-1]
    assert remote.endswith("kanban complete T-1 --result done")


def test_list_tasks_status_filter():
    runner = FakeRunner()
    bridge = KanbanBridge(runner=runner, transport="ssh")
    bridge.list_tasks(status="ready")
    assert runner.calls[0][-1].endswith("kanban list --status ready")


def test_reachable_true_on_success():
    bridge = KanbanBridge(runner=FakeRunner(rc=0), transport="ssh")
    assert bridge.reachable() is True


def test_reachable_false_on_transport_error():
    bridge = KanbanBridge(runner=FakeRunner(raises=FileNotFoundError("no ssh")), transport="ssh")
    assert bridge.reachable() is False


def test_local_create_show_comment_complete_cycle(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "local")
    monkeypatch.setenv("HERMES_KANBAN_BOARD_PATH", str(tmp_path / "board.json"))
    monkeypatch.setenv("HERMES_KANBAN_LOCAL_BIN", "/definitely-missing-hermes")
    bridge = KanbanBridge()

    created = bridge.create_task("title", body="body", assignee="hermes", triage=True)
    assert created.ok is True
    assert created.parsed["id"] == "T-1"
    assert created.parsed["status"] == "triage"

    listed = bridge.list_tasks(status="triage")
    assert listed.parsed[0]["id"] == "T-1"

    commented = bridge.comment("T-1", "looks good", author="atlas")
    assert commented.parsed["comments"][0]["author"] == "atlas"

    completed = bridge.complete("T-1", result="done")
    assert completed.parsed["status"] == "done"
    assert completed.parsed["result"] == "done"

    shown = bridge.show_task("T-1")
    assert shown.parsed["id"] == "T-1"

    stats = bridge.stats()
    assert stats.parsed == {"total": 1, "open": 0, "done": 1}


# ---------------------------------------------------------------------------
# Merkle logging (rule 1)
# ---------------------------------------------------------------------------


def test_success_logged_to_merkle():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(rc=0), transport="ssh")
    bridge.run("boards")
    assert len(merkle.records) == 1
    rec = merkle.records[0]
    assert rec["action"] == "kanban.boards"
    assert rec["agent"] == "kanban_bridge"
    assert rec["result"] == "success"


def test_merkle_payload_fingerprints_arguments_instead_of_recording_content():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(rc=0), transport="ssh")
    secret_body = "private customer material"
    bridge.create_task("title", body=secret_body)
    payload = merkle.records[0]["payload"]
    assert secret_body not in str(payload)
    assert payload["argument_count"] == 4
    assert len(payload["arguments_sha256"]) == 64


def test_failure_logged_to_merkle():
    merkle = FakeMerkle()
    bridge = KanbanBridge(merkle=merkle, runner=FakeRunner(rc=1), transport="ssh")
    bridge.run("complete", "T-9")
    assert merkle.records[0]["result"] == "failure"


def test_transport_error_logged_and_raised():
    merkle = FakeMerkle()
    bridge = KanbanBridge(
        merkle=merkle, runner=FakeRunner(raises=subprocess.TimeoutExpired("ssh", 5)), transport="ssh"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        bridge.run("list")
    assert merkle.records[0]["result"] == "failure"


def test_no_merkle_is_safe():
    bridge = KanbanBridge(merkle=None, runner=FakeRunner(rc=0), transport="ssh")
    res = bridge.run("boards")  # must not raise
    assert res.ok is True
