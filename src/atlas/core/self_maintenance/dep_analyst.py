"""ADR-039 slice 6, paso 4 del roadmap "juicio real para autoauditoría".

Juicio de riesgo para UN bump de dependencia concreto, ANTES de que entre al
lote. Hoy ``DepProposer.propose_bump()`` genera el patch de forma 100%
mecánica (sube el número de versión con una regex) sin que ningún modelo
evalúe si el salto es razonable o arriesgado.

Diferencia deliberada respecto a ``MaintenanceAnalyst`` (mismo estilo, léelo
igual): allí se separan processing-LLM/control-LLM porque digiere PROSA NO
CONFIABLE de fuentes externas (release notes, foros) — hace falta un
processing-LLM que extraiga campos tipados antes de que el control-LLM los
vea. Un ``DepCandidate`` en cambio ya viene tipado y autoritativo de PyPI
(``name``, ``current``, ``latest``, ``source``): no hay prosa que extraer, así
que UN SOLO LLM de control basta para juzgar el riesgo del salto de versión.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from atlas.core.inference_hub import InferenceLevel, InferenceRequest
from atlas.core.self_maintenance.candidate import DepCandidate

_RISK_LEVELS = ("low", "moderate", "high")

_REVIEW_INSTRUCTION = (
    "Evalúa el riesgo de subir una dependencia de versión. Responde SOLO un "
    'objeto JSON {"risk": "low"|"moderate"|"high", "summary": "...", '
    '"concerns": ["..."]}. Sube "high" solo si el salto de versión mayor '
    "sugiere cambios de API incompatibles (ej. 1.x -> 2.x); \"low\" para "
    "parches/menores."
)


@dataclass
class DepReviewVerdict:
    """Veredicto de riesgo sobre un bump concreto. ``risk="unknown"`` si el
    LLM no respondió algo confiable — nunca se traduce en bloqueo aguas
    arriba, solo en falta de señal."""

    risk: str  # "low" | "moderate" | "high" | "unknown"
    summary: str = ""
    concerns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"risk": self.risk, "summary": self.summary, "concerns": list(self.concerns)}


class DepAnalyst:
    """Juicio de UN SOLO LLM (ver docstring del módulo: sin separación
    dual-LLM, ``DepCandidate`` no trae prosa no confiable) sobre el riesgo de
    un bump de dependencia concreto. Señal para el humano que revisa el lote,
    NUNCA gate: nunca bloquea ``propose_bump()``."""

    AGENT = "self_maintenance.dep_analyst"

    def __init__(self, *, hub: Any, merkle: Any | None = None) -> None:
        self._hub = hub
        self._merkle = merkle

    def review(self, candidate: DepCandidate) -> DepReviewVerdict:
        prompt = (
            f"{_REVIEW_INSTRUCTION}\n\n{candidate.name}: {candidate.current} -> {candidate.latest}"
        )
        try:
            resp = self._hub.infer(InferenceRequest(
                prompt=prompt,
                level=InferenceLevel.L1,
                temperature=0.0,
                task_id="dep_analyst.review",
            ))
        except Exception:  # noqa: BLE001 — señal, no gate; nunca bloquea
            return DepReviewVerdict(risk="unknown")

        if not resp.success:
            return DepReviewVerdict(risk="unknown")

        data = _parse_json_object(resp.text)
        if data is None or data.get("risk") not in _RISK_LEVELS:
            return DepReviewVerdict(risk="unknown")

        return DepReviewVerdict(
            risk=data["risk"],
            summary=str(data.get("summary", "")),
            concerns=[str(c) for c in (data.get("concerns") or [])],
        )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extrae el primer objeto JSON del texto del modelo. Tolerante a prosa
    alrededor; ``None`` si no parsea (→ risk="unknown" aguas arriba)."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None
