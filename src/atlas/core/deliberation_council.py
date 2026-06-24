"""
Cónclave (deliberation_council) — adaptador de deliberación multi-voz.

Envuelve proveedores de `InferenceHub` como revisores hostiles concretos
(`LlmReviewer`), los ensambla en un trío de linajes distintos
(`build_trio_reviewers`) y los convoca sobre una decisión humana con gating y
veredicto honesto (`convene_for_decision`) usando `adversarial_panel` (ADR-047).

Disciplina (de esta casa): diversidad obligatoria (sin 3 proveedores distintos
vivos → UNKNOWN, no se miente) y gating (lo trivial no quema modelos). El juez
(la silla) NO es una voz del panel: preside y sintetiza fuera de aquí.
"""

from __future__ import annotations

from atlas.core.adversarial_panel import Objection, Severity
from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest

_HOSTILE_PROMPT = (
    "Eres un revisor hostil. Ataca esta decisión: ¿qué rompe, qué asume falso, "
    "qué caso límite ignora? Responde en la PRIMERA línea SOLO con una de: "
    "NONE MINOR MAJOR BLOCKING. En las siguientes líneas, la objeción concreta.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)
_SEVERITIES = {s.name: s for s in Severity}


class LlmReviewer:
    """Reviewer concreto: envuelve UN proveedor de InferenceHub con prompt hostil.

    Cumple el Protocol `adversarial_panel.Reviewer` (reviewer_id/provider/review).
    Mapea la respuesta a `Severity` por la 1ª línea; una respuesta ilegible o una
    llamada fallida → `Severity.MAJOR` (fail-closed: una objeción que no se puede
    leer no se trata como "sin objeción").
    """

    def __init__(
        self,
        reviewer_id: str,
        provider: str,
        hub: InferenceHub,
        level: InferenceLevel,
    ) -> None:
        self._id = reviewer_id
        self._provider = provider
        self._hub = hub
        self._level = level

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._provider

    def review(self, diff: str, context: str = "") -> Objection:
        resp = self._hub.infer(
            InferenceRequest(
                prompt=_HOSTILE_PROMPT.format(diff=diff, context=context),
                level=self._level,
            )
        )
        if not resp.success or not resp.text.strip():
            return Objection(
                self._id, self._provider, Severity.MAJOR,
                "revisión no disponible (fail-closed)",
            )
        lines = resp.text.strip().splitlines()
        sev = _SEVERITIES.get(lines[0].strip().upper(), Severity.MAJOR)
        detail = "\n".join(lines[1:]).strip()
        return Objection(self._id, self._provider, sev, detail)
