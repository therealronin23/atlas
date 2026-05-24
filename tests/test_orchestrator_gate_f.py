"""Tests Gate F — Orchestrator routing for browser/editor/vision tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus
from atlas.core.orchestrator import Orchestrator
from atlas.tools.computer_use.vision_loop import ProposedAction


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    return Orchestrator(workspace=tmp_path / "atlas")


@dataclass
class DummyNavigation:
    url: str
    title: str = "Dummy"
    text: str = "dummy text"
    status_code: int = 200
    duration_ms: int = 1


class DummyBrowser:
    def __init__(self) -> None:
        self.navigated_to: str | None = None

    def navigate(self, url: str) -> DummyNavigation:
        self.navigated_to = url
        return DummyNavigation(url=url)


class DummyVisionLoop:
    def propose_next(self, screenshot_name: str = "vision_loop") -> ProposedAction:
        return ProposedAction(
            kind="stop",
            reason=f"observed {screenshot_name}",
            requires_approval=False,
        )


def test_editor_read_executes_without_approval(orch: Orchestrator) -> None:
    target = Path(orch.status().workspace) / "projects" / "note.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("atlas gate f")

    task = orch.handle_intent("editor read projects/note.txt")

    assert task.status == TaskStatus.DONE
    assert task.route == RoutingLevel.DETERMINISTIC_TOOL
    assert task.tool_name == "editor.read"
    assert task.result["success"] is True
    assert task.result["content"] == "atlas gate f"


def test_editor_write_requires_approval_then_executes(orch: Orchestrator) -> None:
    task = orch.handle_intent("editor write projects/out.txt :: hello gate f")

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL
    assert task.tool_name == "editor.write"
    assert orch.pending_approvals()[0]["task_id"] == task.id

    approved = orch.approve_pending(task.id, approved=True)

    assert approved["status"] == TaskStatus.DONE.value
    assert (Path(orch.status().workspace) / "projects" / "out.txt").read_text() == "hello gate f"


def test_editor_run_uses_executor_after_approval(orch: Orchestrator) -> None:
    task = orch.handle_intent("editor run tmp :: echo hello")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    orch.approve_pending(task.id, approved=True)

    assert task.status == TaskStatus.DONE
    assert task.result["success"] is True
    assert "hello" in task.result["stdout"]
    exec_logs = [r for r in orch._merkle.tail(20) if r.action == "exec.command"]
    assert exec_logs
    assert exec_logs[-1].agent == "atlas.executor"


def test_browser_navigation_is_pending_until_approved(orch: Orchestrator) -> None:
    browser = DummyBrowser()
    orch.attach_gate_f_tools(browser=browser)

    task = orch.handle_intent("browser navigate https://example.com")

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL
    assert task.tool_name == "browser.navigate"
    assert browser.navigated_to is None

    orch.approve_pending(task.id, approved=True)

    assert task.status == TaskStatus.DONE
    assert browser.navigated_to == "https://example.com"
    assert task.result["status_code"] == 200


def test_vision_propose_executes_as_observation(orch: Orchestrator) -> None:
    orch.attach_gate_f_tools(vision_loop=DummyVisionLoop())

    task = orch.handle_intent("vision propose smoke")

    assert task.status == TaskStatus.DONE
    assert task.route == RoutingLevel.DETERMINISTIC_TOOL
    assert task.tool_name == "vision.propose"
    assert task.result["kind"] == "stop"
    assert task.result["requires_approval"] is False
