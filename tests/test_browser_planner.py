"""Tests for src/atlas/tools/browser_use/browser_planner.py."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest, InferenceResponse
from atlas.tools.browser_use.browser_planner import BrowserPlanner


@dataclass(frozen=True)
class _FakeInferenceHub(InferenceHub):
    mock_responses: list[InferenceResponse]

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        if not self.mock_responses:
            return InferenceResponse(success=False, error="No mock responses left")
        return self.mock_responses.pop(0)

    def select_model(self, level: InferenceLevel) -> str:
        return "fake_model"


def test_browser_planner_valid_plan() -> None:
    plan_json = json.dumps({
        "steps": [
            {"kind": "navigate", "url": "https://example.com", "reason": "Go to site"},
            {"kind": "click", "selector": "#btn", "reason": "Click button"},
            {"kind": "stop", "reason": "Done"}
        ]
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
    planner = BrowserPlanner(hub=hub)
    actions = planner.plan(instruction="Haz click en el boton")

    assert len(actions) == 3
    assert actions[0].kind == "navigate"
    assert actions[0].url == "https://example.com"
    assert actions[0].requires_approval is True

    assert actions[1].kind == "click"
    assert actions[1].selector == "#btn"
    assert actions[1].requires_approval is True

    assert actions[2].kind == "stop"
    assert actions[2].reason == "Done"
    assert actions[2].requires_approval is False


def test_browser_planner_invalid_json() -> None:
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
    planner = BrowserPlanner(hub=hub)
    actions = planner.plan(instruction="Haz algo")

    assert len(actions) == 1
    assert actions[0].kind == "stop"
    assert "inválido" in actions[0].reason
    assert actions[0].requires_approval is False


def test_browser_planner_model_failure() -> None:
    hub = _FakeInferenceHub(
        mock_responses=[
            InferenceResponse(
                success=False,
                text="",
                error="Network error",
                provider="test",
                model="test",
                level=InferenceLevel.L1,
                latency_ms=10,
            )
        ]
    )
    planner = BrowserPlanner(hub=hub)
    actions = planner.plan(instruction="Haz algo")

    assert len(actions) == 1
    assert actions[0].kind == "stop"
    assert "no obtuvo respuesta" in actions[0].reason
