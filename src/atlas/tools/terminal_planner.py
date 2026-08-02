"""
Atlas Core — TerminalPlanner (T3.3).

Genera comandos bash iterativamente a partir de un objetivo en lenguaje
natural, para ser ejecutados dentro de LayeredIsolationSandbox.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest


@dataclass(frozen=True)
class TerminalAction:
    kind: Literal["stop", "run_bash"]
    reason: str
    script: str | None = None
    requires_approval: bool = True


def normalize_terminal_approval(action: TerminalAction) -> TerminalAction:
    """
    Invariante D2: La aprobación la decide el código.
    Cualquier comando bash requiere aprobación o ser ejecutado en sandbox
    con permisos acotados. Por defecto, requiere aprobación.
    """
    if action.kind == "stop":
        return TerminalAction(
            kind=action.kind,
            reason=action.reason,
            script=None,
            requires_approval=False,
        )
    return TerminalAction(
        kind=action.kind,
        reason=action.reason,
        script=action.script,
        requires_approval=True,
    )


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_PROMPT = """\
Eres un planificador de operaciones de terminal (bash). Tu objetivo es: {instruction}

## Salida del último comando ejecutado
{observation}

Responde EXCLUSIVAMENTE con un JSON con esta forma exacta, sin explicar nada más:
{{"action": {{"kind": "run_bash", "script": "ls -la", "reason": "Ver directorio"}}}}

kind válidos: stop, run_bash.
- run_bash necesita script (el código bash a ejecutar).
- stop no necesita script, solo reason indicando por qué terminaste o si hay un error.\
"""


class _TerminalPlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["stop", "run_bash"]
    reason: str
    script: str | None = None


class _TerminalPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: _TerminalPlanStepModel


def _extract_json(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    return match.group(1) if match else text


class TerminalPlanner:
    def __init__(self, hub: InferenceHub) -> None:
        self._hub = hub

    def plan(self, instruction: str, observation: str = "") -> TerminalAction:
        prompt = _PROMPT.format(
            instruction=instruction, observation=observation,
        )
        request = InferenceRequest(
            prompt=prompt, level=InferenceLevel.L1,
            task_id="terminal_planner", max_tokens=1024,
        )
        response = self._hub.infer_for_role("plan", request)
        if not response.success:
            return normalize_terminal_approval(TerminalAction(kind="stop", reason="Sin respuesta del modelo."))
        
        try:
            raw = json.loads(_extract_json(response.text))
            parsed = _TerminalPlanModel.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            return normalize_terminal_approval(TerminalAction(kind="stop", reason="Plan del modelo inválido."))

        return normalize_terminal_approval(
            TerminalAction(
                kind=parsed.action.kind,
                reason=parsed.action.reason,
                script=parsed.action.script,
            )
        )
