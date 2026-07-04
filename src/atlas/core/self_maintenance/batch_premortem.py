"""Paso 2 del roadmap "juicio real para autoauditoría" (tras PreflightGate,
determinista/CVEs+conexión). Este es el PRIMER paso con juicio real (LLM), y
va ANTES de que ``ColdUpdateBatcher`` pague el coste de correr la suite
completa de tests sobre el lote combinado.

Corrección del Cónclave que motiva esto: un premortem con juicio podría
advertir el riesgo de COMBINAR varios cambios ya válidos por separado, más
barato que esperar a que fallen los tests.

Mismo patrón dual-LLM que ``analyst.py`` (ADR-039 slice 2): un LLM barato
(``self._hub.infer``) razona sobre JSON tipado en el camino normal. Camino de
escalada: si el lote toca una ruta sensible, se convoca al Cónclave completo
(``convene_for_decision``, trío) en vez de confiar en un solo modelo barato —
mismo principio de gating adaptativo que ``deliberation_council.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atlas.core.deliberation_council import convene_for_decision
from atlas.core.inference_hub import InferenceLevel, InferenceRequest
from atlas.router.cascade import Difficulty

# Rutas que, si algún patch del lote las toca, fuerzan escalar al Cónclave
# completo (trío) en vez de la revisión barata de un solo LLM — mismo
# principio de gating adaptativo que ya usa deliberation_council.py: el
# trío es la escalada cara, no el pan de cada día.
_SENSITIVE_PATH_MARKERS = (
    "cold_update_manager.py",
    "governance",
    "decider",
    "security/",
    "tier1_auto_apply",
)

_PREMORTEM_INSTRUCTION = (
    "Estos son varios cambios YA válidos por separado que se van a combinar en "
    "un solo lote. Razona SOLO sobre riesgos de la COMBINACIÓN (interacciones, "
    "colisiones, efectos acumulados) y responde con un objeto JSON "
    '{"verdict": "ok"|"concern", "risk_flags": [strings cortos]}. Nada más.'
)

# Recorte de diffs concatenados para no disparar el coste/latencia del LLM
# barato ni el contexto de convene_for_decision con lotes enormes.
_MAX_CONTEXT_CHARS = 8000


@dataclass
class PremortemResult:
    escalated: bool                 # True si se convocó al Cónclave completo (trío)
    verdict: str                    # "ok" | "concern" | "unknown"
    risk_flags: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "escalated": self.escalated,
            "verdict": self.verdict,
            "risk_flags": list(self.risk_flags),
            "reason": self.reason,
        }


class BatchPremortemGate:
    """Premortem barato ANTES de correr tests caros sobre un lote combinado.

    Camino normal: un solo LLM barato (mismo patrón dual-LLM que
    MaintenanceAnalyst) razona sobre los intents+diffs combinados y devuelve
    un JSON tipado con riesgos. Camino de escalada: si algún patch del lote
    toca una ruta sensible (ver _SENSITIVE_PATH_MARKERS), se convoca al
    Cónclave completo (convene_for_decision con el trío) en vez de confiar
    en un solo modelo barato.

    Fail-open intencional: esto es una SEÑAL adicional antes de los tests,
    NO un gate duro que reemplace la validación real — ValidationRunner/
    ColdUpdateBatcher siguen corriendo los tests igual pase lo que pase aquí.
    """

    AGENT = "self_maintenance.batch_premortem"

    def __init__(
        self,
        *,
        hub: Any,
        merkle: Any,
        synthesis_recorder: Any | None = None,
        convene_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._hub = hub
        self._merkle = merkle
        self._synthesis_recorder = synthesis_recorder
        # Inyectable para tests (evita red/trío real); default: el real.
        self._convene_fn = convene_fn if convene_fn is not None else convene_for_decision

    def assess(self, proposals: list[Any]) -> PremortemResult:
        """`proposals`: lista de ColdUpdateProposal (o duck-typed con .intent/.patch_path/.id)."""
        if self._touches_sensitive_path(proposals):
            return self._escalate(proposals)
        return self._cheap_assess(proposals)

    # ------------------------------------------------------------------
    # camino normal: un solo LLM barato, fail-open si no parsea/falla
    # ------------------------------------------------------------------

    def _cheap_assess(self, proposals: list[Any]) -> PremortemResult:
        context = self._combined_context(proposals)
        prompt = f"{_PREMORTEM_INSTRUCTION}\n\n{context}"
        try:
            resp = self._hub.infer(InferenceRequest(
                prompt=prompt,
                level=InferenceLevel.L1,
                temperature=0.0,
                task_id="batch_premortem",
            ))
        except Exception:  # noqa: BLE001 — señal adicional, nunca crashea
            return PremortemResult(escalated=False, verdict="unknown")

        if not resp.success:
            return PremortemResult(escalated=False, verdict="unknown")

        data = _parse_json_object(resp.text)
        if data is None:
            return PremortemResult(escalated=False, verdict="unknown")

        verdict = data.get("verdict")
        if verdict not in ("ok", "concern"):
            return PremortemResult(escalated=False, verdict="unknown")

        raw_flags = data.get("risk_flags") or []
        risk_flags = [str(f).strip() for f in raw_flags if str(f).strip()] if isinstance(raw_flags, list) else []
        return PremortemResult(escalated=False, verdict=verdict, risk_flags=risk_flags)

    # ------------------------------------------------------------------
    # camino de escalada: Cónclave completo (trío) sobre rutas sensibles
    # ------------------------------------------------------------------

    def _escalate(self, proposals: list[Any]) -> PremortemResult:
        decision = "Lote de cambios combinados: " + "; ".join(
            getattr(p, "intent", "") for p in proposals
        )
        context = self._combined_context(proposals)

        kwargs: dict[str, Any] = dict(
            decision=decision,
            context=context,
            difficulty=Difficulty.HARD,
            risk="high",
        )
        if self._synthesis_recorder is not None:
            kwargs["synthesis_recorder"] = self._synthesis_recorder

        try:
            evidence = self._convene_fn(**kwargs)
        except Exception:  # noqa: BLE001 — fail-open: señal, no gate duro
            return PremortemResult(escalated=False, verdict="unknown")

        # gating dijo no escalar (trivial-reversible), o sin evidencia real:
        # no bloquea, se trata como señal desconocida.
        if evidence is None:
            return PremortemResult(escalated=False, verdict="unknown")

        return PremortemResult(
            escalated=True,
            verdict="concern",
            reason=getattr(evidence, "reason", ""),
        )

    # ------------------------------------------------------------------

    def _touches_sensitive_path(self, proposals: list[Any]) -> bool:
        for p in proposals:
            patch_path = getattr(p, "patch_path", None)
            if not patch_path:
                continue
            try:
                text = Path(patch_path).read_text()
            except OSError:
                continue
            if any(marker in text for marker in _SENSITIVE_PATH_MARKERS):
                return True
        return False

    def _combined_context(self, proposals: list[Any]) -> str:
        parts: list[str] = []
        for p in proposals:
            intent = getattr(p, "intent", "")
            patch_path = getattr(p, "patch_path", None)
            diff_text = ""
            if patch_path:
                try:
                    diff_text = Path(patch_path).read_text()
                except OSError:
                    diff_text = ""
            parts.append(f"# intent: {intent}\n{diff_text}")
        combined = "\n\n".join(parts)
        return combined[:_MAX_CONTEXT_CHARS]


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extrae el primer objeto JSON del texto del modelo. Tolerante a prosa
    alrededor; ``None`` si no parsea (fail-open aguas arriba, verdict=unknown)."""
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
