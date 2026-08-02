"""
Atlas Core — BrowserPlanner (T3-2).

Genera un plan de pasos (BrowserAction) a partir de una instrucción en
lenguaje natural para el navegador (Playwright).
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from atlas.tools.browser_use.browser_action import BrowserAction, normalize_browser_approval

MAX_PLAN_STEPS = 10

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_PROMPT = """\
Eres un planificador de acciones de navegador web. Genera un plan de como \
máximo {max_steps} pasos para lograr: {instruction}

## Observación actual del DOM / Pantalla
{observation}

Responde EXCLUSIVAMENTE con un JSON con esta forma exacta, sin explicar nada más:
{{"steps": [{{"kind": "click", "selector": "#boton", "reason": "..."}}, ...]}}

kind válidos: stop, navigate, click, fill, extract, screenshot.
- navigate necesita url.
- click necesita selector.
- fill necesita selector y value.
- screenshot necesita name.
- extract no necesita campos extra (solo reason).
- stop no necesita nada más que reason.\
"""


class _BrowserPlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["stop", "navigate", "click", "fill", "extract", "screenshot"]
    reason: str
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    name: str | None = None


class _BrowserPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[_BrowserPlanStepModel]


def _stop_plan(reason: str) -> list[BrowserAction]:
    return [normalize_browser_approval(BrowserAction(kind="stop", reason=reason))]


def _extract_json(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    return match.group(1) if match else text


class BrowserPlanner:
    def __init__(self, hub: InferenceHub, *, max_steps: int = MAX_PLAN_STEPS) -> None:
        self._hub = hub
        self._max_steps = max_steps

    def plan(self, instruction: str, observation: str = "") -> list[BrowserAction]:
        prompt = _PROMPT.format(
            max_steps=self._max_steps, instruction=instruction, observation=observation,
        )
        request = InferenceRequest(
            prompt=prompt, level=InferenceLevel.L1,
            task_id="browser_planner", max_tokens=1024,
        )
        response = self._hub.infer_for_role("plan", request)
        if not response.success:
            return _stop_plan("El planificador no obtuvo respuesta del modelo.")
        return self._parse(response.text)

    def _parse(self, text: str) -> list[BrowserAction]:
        try:
            raw = json.loads(_extract_json(text))
            parsed = _BrowserPlanModel.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            return _stop_plan("Plan del modelo inválido (JSON malformado o campo desconocido).")

        steps = parsed.steps[: self._max_steps]
        return [
            normalize_browser_approval(
                BrowserAction(
                    kind=step.kind, reason=step.reason, url=step.url,
                    selector=step.selector, value=step.value, name=step.name,
                )
            )
            for step in steps
        ]
