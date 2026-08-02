"""Tests for src/atlas/tools/terminal_planner.py."""
from __future__ import annotations

import json
from dataclasses import dataclass

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest, InferenceResponse
from atlas.tools.terminal_planner import TerminalPlanner


@dataclass(frozen=True)
class _FakeInferenceHub(InferenceHub):
    mock_responses: list[InferenceResponse]

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        if not self.mock_responses:
            return InferenceResponse(
                success=False, text="", error="No mock responses left",
                provider="test", model="test", level=InferenceLevel.L1, latency_ms=10
            )
        return self.mock_responses.pop(0)

    def select_model(self, level: InferenceLevel) -> str:
        return "fake_model"


def test_terminal_planner_valid_plan() -> None:
    plan_json = json.dumps({
        "action": {"kind": "run_bash", "script": "ls -la", "reason": "Check files"}
    })
    hub = _FakeInferenceHub(
        mock_responses=[
            InferenceResponse(
                success=True,
                text=f"```json\n{plan_json}\n```",
                provider="test",
                model="test",
                level=InferenceLevel.L1,
                latency_ms=10,
            )
        ]
    )
    planner = TerminalPlanner(hub=hub)
    action = planner.plan(instruction="Mira los archivos")

    assert action.kind == "run_bash"
    assert action.script == "ls -la"
    assert action.requires_approval is True


def test_terminal_planner_stop_plan() -> None:
    plan_json = json.dumps({
        "action": {"kind": "stop", "reason": "Done"}
    })
    hub = _FakeInferenceHub(
        mock_responses=[
            InferenceResponse(
                success=True,
                text=f"```json\n{plan_json}\n```",
                provider="test",
                model="test",
                level=InferenceLevel.L1,
                latency_ms=10,
            )
        ]
    )
    planner = TerminalPlanner(hub=hub)
    action = planner.plan(instruction="Termina")

    assert action.kind == "stop"
    assert action.script is None
    assert action.requires_approval is False


def test_terminal_planner_invalid_json() -> None:
    hub = _FakeInferenceHub(
        mock_responses=[
            InferenceResponse(
                success=True,
                text="```json\n{bad_json\n```",
                provider="test",
                model="test",
                level=InferenceLevel.L1,
                latency_ms=10,
            )
        ]
    )
    planner = TerminalPlanner(hub=hub)
    action = planner.plan(instruction="Haz algo")

    assert action.kind == "stop"
    assert "inválido" in action.reason
    assert action.requires_approval is False
