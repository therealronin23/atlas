"""
Atlas Core — DesktopPlanner (Gate F/desktop, t3-1-universal-gui-operator).

Genera un plan de N pasos (DesktopAction) a partir de una instrucción en
lenguaje natural — mismo patrón que AtlasCoder (prompt fijo + InferenceHub
+ parseo estricto fail-closed), pero con salida JSON tipada (pydantic,
extra="forbid" — mismo patrón que AtlasAdapter en
atlas.mcp.adapter_registry) en vez de bloques SEARCH/REPLACE de texto.

Invariante D2 (juicio LLM nunca en autorización): el schema de entrada NO
tiene un campo requires_approval — el LLM no puede proponerlo. Cada paso
válido se convierte a DesktopAction y pasa por normalize_desktop_approval()
antes de devolverse; la aprobación la decide siempre el código. Cualquier
fallo de parseo (JSON inválido, campo desconocido, kind fuera del literal)
produce un plan de un solo paso [stop], nunca ejecución adivinada.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from atlas.tools.computer_use.desktop_action import DesktopAction, normalize_desktop_approval

MAX_PLAN_STEPS = 10

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_PROMPT = """\
Eres un planificador de acciones de escritorio. Genera un plan de como \
máximo {max_steps} pasos para lograr: {instruction}

## Observación actual de la pantalla
{observation}

Responde EXCLUSIVAMENTE con un JSON con esta forma exacta, sin explicar
nada más:
{{"steps": [{{"kind": "click", "x": 100, "y": 200, "reason": "..."}}, ...]}}

kind válidos: stop, click, type, key, move, scroll, drag.
- click/move/scroll/drag necesitan x/y.
- type necesita text.
- key necesita key_combo.
- stop no necesita nada más que reason.\
"""


class _DesktopPlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["stop", "click", "type", "key", "move", "scroll", "drag"]
    reason: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key_combo: str | None = None


class _DesktopPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[_DesktopPlanStepModel]


def _stop_plan(reason: str) -> list[DesktopAction]:
    return [normalize_desktop_approval(DesktopAction(kind="stop", reason=reason))]


def _extract_json(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    return match.group(1) if match else text


class DesktopPlanner:
    def __init__(self, hub: InferenceHub, *, max_steps: int = MAX_PLAN_STEPS) -> None:
        self._hub = hub
        self._max_steps = max_steps

    def plan(self, instruction: str, observation: str = "") -> list[DesktopAction]:
        prompt = _PROMPT.format(
            max_steps=self._max_steps, instruction=instruction, observation=observation,
        )
        request = InferenceRequest(
            prompt=prompt, level=InferenceLevel.L1,
            task_id="desktop_planner", max_tokens=1024,
        )
        response = self._hub.infer_for_role("plan", request)
        if not response.success:
            return _stop_plan("El planificador no obtuvo respuesta del modelo.")
        return self._parse(response.text)

    def _parse(self, text: str) -> list[DesktopAction]:
        try:
            raw = json.loads(_extract_json(text))
            parsed = _DesktopPlanModel.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            return _stop_plan("Plan del modelo inválido (JSON malformado o campo desconocido).")

        steps = parsed.steps[: self._max_steps]
        return [
            normalize_desktop_approval(
                DesktopAction(
                    kind=step.kind, reason=step.reason, x=step.x, y=step.y,
                    text=step.text, key_combo=step.key_combo,
                )
            )
            for step in steps
        ]
