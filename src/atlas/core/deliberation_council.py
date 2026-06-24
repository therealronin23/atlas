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

from atlas.core.adversarial_panel import (
    AdversarialPanel,
    Objection,
    Reviewer,
    Severity,
    should_convene,
)
from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
    Provider,
)
from atlas.core.verify import Evidence
from atlas.router.cascade import Difficulty

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


# El trío: tres linajes ortogonales (🇺🇸 Gemini · 🇨🇳 Kimi · 🇪🇺 Mistral).
# La distancia entre linajes maximiza la señal de desacuerdo útil.
_TRIO_NAMES = ("gemini_free", "nvidia_kimi", "nvidia_mistral_large")


def build_trio_reviewers(providers: list[Provider] | None = None) -> list[Reviewer]:
    """Ensambla el trío de revisores, uno por proveedor de linaje distinto.

    Cada reviewer recibe un `InferenceHub` de UN solo proveedor (así `infer`
    llama solo a ese, sin fallback cruzado). Si falta un proveedor del trío en
    el pool, queda fuera — el panel detectará la falta de diversidad y emitirá
    UNKNOWN aguas abajo (no se finge un trío incompleto).
    """
    pool = {p.name: p for p in (providers or DEFAULT_PROVIDERS)}
    out: list[Reviewer] = []
    for name in _TRIO_NAMES:
        p = pool.get(name)
        if p is None:
            continue
        out.append(LlmReviewer(name, name, InferenceHub(providers=[p]), p.level))
    return out


def convene_for_decision(
    decision: str,
    context: str = "",
    *,
    difficulty: Difficulty,
    risk: str,
    irreversible: bool = False,
    reviewers: list[Reviewer] | None = None,
) -> Evidence | None:
    """Convoca el trío sobre una decisión, con gating y diversidad obligatoria.

    Devuelve `None` si el gating dice que NO escale (lo trivial-reversible no
    quema modelos). Si escala, corre el panel exigiendo 3 proveedores distintos;
    sin esa diversidad el panel devuelve `Verdict.UNKNOWN` (unknown > mentir).
    """
    if not should_convene(difficulty, risk, irreversible=irreversible):
        return None
    panel = AdversarialPanel(reviewers or build_trio_reviewers(), min_providers=3)
    return panel.verify(decision, context)
