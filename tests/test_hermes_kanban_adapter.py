from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import Task, TaskSource, TaskStatus
from atlas.core.orchestrator import Orchestrator
from atlas.hermes.hermes import (
    DelegationBuilder,
    HermesKanbanAdapter,
    HermesUnreachable,
    OfflineQueue,
)


class _FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._reachable = True

    def reachable(self) -> bool:
        return self._reachable

    def create_task(self, title: str, body: str = "", assignee: str | None = None, triage: bool = False):
        self.calls.append(("create_task", (title,), {"body": body, "assignee": assignee, "triage": triage}))
        return type("Res", (), {"ok": True, "parsed": {"id": "t-kanban-1"}, "stderr": ""})()

    def run(self, *args: str):
        self.calls.append(("run", args, {}))
        if args[:2] == ("stats", "--json"):
            return type("Res", (), {"ok": True, "parsed": {"by_status": {"todo": 2, "done": 1}, "oldest_ready_age_seconds": 12}})()
        if args[:4] == ("list", "--status", "ready", "--json"):
            return type("Res", (), {"ok": True, "parsed": [{"id": "t-ready-1"}]})()
        if args[:3] == ("show", "t-kanban-1", "--json"):
            return type("Res", (), {"ok": True, "parsed": {"task": {"id": "t-kanban-1", "status": "todo", "completed_at": None}, "latest_summary": None}})()
        if args[:2] == ("archive", "t-kanban-1"):
            return type("Res", (), {"ok": True, "parsed": None})()
        return type("Res", (), {"ok": False, "parsed": None, "stderr": "boom"})()


def test_enqueue_task_creates_kanban_card() -> None:
    bridge = _FakeBridge()
    adapter = HermesKanbanAdapter(bridge=bridge, assignee="default")

    receipt = adapter.enqueue_task(
        DelegationBuilder.build("task-1", "Investiga el estado del sistema", 3)
    )

    assert receipt.accepted is True
    assert receipt.delegation_id == "t-kanban-1"
    assert bridge.calls[0] == (
        "create_task",
        ("Investiga el estado del sistema",),
        {"body": "Investiga el estado del sistema", "assignee": "default", "triage": False},
    )


def test_enqueue_task_unreachable_falls_to_offline_queue(tmp_path: Path) -> None:
    class _BadBridge(_FakeBridge):
        def create_task(self, title: str, body: str = "", assignee: str | None = None, triage: bool = False):
            self.calls.append(("create_task", (title,), {"body": body, "assignee": assignee, "triage": triage}))
            return type("Res", (), {"ok": False, "parsed": None, "stderr": "kanban down"})()

    queue = OfflineQueue(tmp_path / "memory")
    adapter = HermesKanbanAdapter(bridge=_BadBridge(), offline_queue=queue)

    with pytest.raises(HermesUnreachable):
        adapter.enqueue_task(DelegationBuilder.build("task-1", "Investiga", 3))

    assert queue.depth == 1


def test_status_and_queue_status_use_kanban_stats() -> None:
    adapter = HermesKanbanAdapter(bridge=_FakeBridge())

    status = adapter.health_check()
    queue = adapter.get_queue_status()

    assert status.reachable is True
    assert status.mode == "kanban"
    assert status.queue_depth == 2
    assert queue.depth == 2
    assert queue.next_task_id == "t-ready-1"


def test_cancel_task_archives_card() -> None:
    bridge = _FakeBridge()
    adapter = HermesKanbanAdapter(bridge=bridge)

    assert adapter.cancel_task("t-kanban-1") is True
    assert ("run", ("archive", "t-kanban-1"), {}) in bridge.calls


def test_orchestrator_uses_kanban_without_offline_duplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = _FakeBridge()
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "local")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.setattr("atlas.hermes.hermes.KanbanBridge", lambda: bridge)

    orch = Orchestrator(workspace=tmp_path / "atlas")
    task = Task(intent="Investiga la incidencia del cluster", source=TaskSource.CLI)
    task.transition(TaskStatus.CLASSIFYING)
    task.transition(TaskStatus.ROUTING)
    before = orch._offline_queue.depth

    orch._delegate_to_hermes(task)

    assert task.status == TaskStatus.DELEGATED
    assert task.result is not None
    assert task.result["accepted"] is True
    assert "Hermes kanban (local)" in task.result["note"]
    assert orch._offline_queue.depth == before


def test_orchestrator_selects_explicit_ssh_kanban_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "ssh")
    monkeypatch.setenv("HERMES_SSH_HOST", "root@100.64.0.2")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    orch = object.__new__(Orchestrator)
    orch._offline_queue = OfflineQueue(tmp_path / "memory")

    adapter = Orchestrator._build_hermes_adapter(orch)

    assert isinstance(adapter, HermesKanbanAdapter)
    assert adapter.transport == "ssh"
