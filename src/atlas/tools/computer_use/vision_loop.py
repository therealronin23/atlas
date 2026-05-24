"""
Atlas Core — Conservative visual loop (Gate F/F3).

This module deliberately stops before autonomous action execution:

    BrowserTool screenshot -> screen description -> ProposedAction

Mutating actions are proposals only and require approval by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from atlas.logging.merkle_logger import MerkleLogger
from atlas.tools.browser import BrowserTool, ScreenshotResult


ActionKind = Literal["stop", "click", "fill", "navigate"]


@dataclass(frozen=True)
class ScreenObservation:
    screenshot: ScreenshotResult
    description: str


@dataclass(frozen=True)
class ProposedAction:
    kind: ActionKind
    reason: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    requires_approval: bool = True


class ScreenDescriber(Protocol):
    def describe(self, screenshot: ScreenshotResult) -> str:
        """Return a compact description of the current screen."""


class ActionPlanner(Protocol):
    def propose(self, observation: ScreenObservation) -> ProposedAction:
        """Return the next proposed action without executing it."""


class StubScreenDescriber:
    """Deterministic describer for tests and offline Gate F smoke runs."""

    def describe(self, screenshot: ScreenshotResult) -> str:
        return (
            f"screenshot path={screenshot.path} "
            f"size={screenshot.width}x{screenshot.height} "
            f"bytes={screenshot.bytes_size}"
        )


class StopPlanner:
    """Safe default planner: observe and stop."""

    def propose(self, observation: ScreenObservation) -> ProposedAction:
        return ProposedAction(
            kind="stop",
            reason=f"Observed screen; no autonomous action selected. {observation.description}",
            requires_approval=False,
        )


class VisionLoop:
    """One-step visual loop that proposes actions but never executes them."""

    MUTATING_ACTIONS: frozenset[ActionKind] = frozenset({"click", "fill", "navigate"})

    def __init__(
        self,
        browser: BrowserTool,
        *,
        describer: ScreenDescriber | None = None,
        planner: ActionPlanner | None = None,
        merkle: MerkleLogger | None = None,
    ) -> None:
        self._browser = browser
        self._describer = describer or StubScreenDescriber()
        self._planner = planner or StopPlanner()
        self._merkle = merkle

    def propose_next(self, screenshot_name: str = "vision_loop") -> ProposedAction:
        screenshot = self._browser.screenshot(screenshot_name)
        description = self._describer.describe(screenshot)
        observation = ScreenObservation(screenshot=screenshot, description=description)
        proposal = self._planner.propose(observation)
        proposal = self._normalize_approval(proposal)
        self._log(observation, proposal)
        return proposal

    def _normalize_approval(self, proposal: ProposedAction) -> ProposedAction:
        if proposal.kind not in self.MUTATING_ACTIONS:
            return ProposedAction(
                kind=proposal.kind,
                reason=proposal.reason,
                selector=proposal.selector,
                value=proposal.value,
                url=proposal.url,
                requires_approval=False,
            )
        return ProposedAction(
            kind=proposal.kind,
            reason=proposal.reason,
            selector=proposal.selector,
            value=proposal.value,
            url=proposal.url,
            requires_approval=True,
        )

    def _log(self, observation: ScreenObservation, proposal: ProposedAction) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action="vision.proposed_action",
            agent="vision.loop",
            result="pending" if proposal.requires_approval else "ok",
            risk_level="medium" if proposal.requires_approval else "safe",
            payload={
                "screenshot": observation.screenshot.path,
                "description_chars": len(observation.description),
                "action": proposal.kind,
                "requires_approval": proposal.requires_approval,
                "selector": proposal.selector,
                "url": proposal.url,
            },
        )
