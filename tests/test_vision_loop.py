"""Tests Gate F/F3 — conservative visual loop."""

from __future__ import annotations

from pathlib import Path

from atlas.logging.merkle_logger import MerkleLogger
from atlas.tools.browser import ScreenshotResult
from atlas.tools.computer_use.vision_loop import (
    ProposedAction,
    ScreenObservation,
    StopPlanner,
    StubScreenDescriber,
    VisionLoop,
)


class DummyBrowser:
    def __init__(self, path: Path) -> None:
        self.path = path

    def screenshot(self, name: str = "vision_loop") -> ScreenshotResult:
        target = self.path / f"{name}.png"
        target.write_bytes(b"fake-png")
        return ScreenshotResult(
            path=str(target),
            width=800,
            height=600,
            bytes_size=8,
        )


class ClickPlanner:
    def propose(self, _observation: ScreenObservation) -> ProposedAction:
        return ProposedAction(
            kind="click",
            selector="#submit",
            reason="submit button detected",
            requires_approval=False,
        )


def test_stub_describer_is_deterministic(tmp_path: Path) -> None:
    screenshot = ScreenshotResult(
        path=str(tmp_path / "screen.png"),
        width=100,
        height=50,
        bytes_size=123,
    )

    description = StubScreenDescriber().describe(screenshot)

    assert "screen.png" in description
    assert "100x50" in description


def test_default_loop_observes_and_stops(tmp_path: Path) -> None:
    loop = VisionLoop(browser=DummyBrowser(tmp_path))  # type: ignore[arg-type]

    action = loop.propose_next()

    assert action.kind == "stop"
    assert action.requires_approval is False


def test_mutating_action_is_forced_to_require_approval(tmp_path: Path) -> None:
    loop = VisionLoop(
        browser=DummyBrowser(tmp_path),  # type: ignore[arg-type]
        planner=ClickPlanner(),
    )

    action = loop.propose_next()

    assert action.kind == "click"
    assert action.selector == "#submit"
    assert action.requires_approval is True


def test_proposed_action_is_logged(tmp_path: Path) -> None:
    merkle = MerkleLogger(tmp_path / "logs")
    loop = VisionLoop(
        browser=DummyBrowser(tmp_path),  # type: ignore[arg-type]
        planner=StopPlanner(),
        merkle=merkle,
    )

    loop.propose_next("logged")

    records = merkle.tail(5)
    assert records[-1].action == "vision.proposed_action"
    assert records[-1].agent == "vision.loop"
    assert records[-1].payload["action"] == "stop"
