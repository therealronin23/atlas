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

from typing import Any, Protocol

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
        first_norm = lines[0].strip().strip("[](){}*#:.- ").upper() if lines else ""
        if first_norm in _SEVERITIES:
            sev = _SEVERITIES[first_norm]
            detail = "\n".join(lines[1:]).strip()
        else:
            # 1a línea no es severidad limpia: fail-closed MAJOR, pero CONSERVA el
            # texto completo (no tirar lines[0], que es el contenido real de la voz).
            # Anclado a 1a línea a propósito: NO escanear el cuerpo (evita el falso
            # positivo "no es MAJOR").
            sev = Severity.MAJOR
            detail = resp.text.strip()
        return Objection(self._id, self._provider, sev, detail)


# El trío: tres linajes ortogonales (🇺🇸 Gemini · 🇨🇳 GLM · 🇪🇺 Mistral).
# La distancia entre linajes maximiza la señal de desacuerdo útil.
# 2026-07-10: asiento CN re-mapeado nvidia_kimi → nvidia_glm (kimi-k2.6 404
# por-cuenta en todo el pool dos días seguidos; glm-5.2 prove-it en vivo).
_TRIO_NAMES = ("gemini_free", "nvidia_glm", "nvidia_mistral_large")

# v2.0.5 — fallback por-linaje: cada slot acepta una lista ORDENADA de
# proveedores del MISMO linaje (mapa investigado en vivo, no re-verificar
# aquí). Si el primario no está en el pool (ej. sin su API key), se usa el
# primer fallback de esa MISMA lista que sí esté disponible — nunca se cruza
# de linaje (cruzar linajes rompe la ortogonalidad que hace útil el desacuerdo).
# 🇺🇸 US: gemini_free (primary) -> groq_llama_70b (fallback, confirmado vivo).
# 🇨🇳 CN: nvidia_glm (primary) -> groq_qwen3 (fallback, confirmado vivo).
# 🇪🇺 EU: nvidia_mistral_large SIN fallback no-NIM vivo confirmado — MISTRAL_API_KEY
#         no está configurada y no hay un ID de OpenRouter verificado para Mistral
#         Large; hueco real, documentado aquí a propósito (no se fabrica uno falso).
_TRIO_LINEAGE_FALLBACKS: dict[str, tuple[str, ...]] = {
    "gemini_free": ("gemini_free", "groq_llama_70b"),
    "nvidia_glm": ("nvidia_glm", "groq_qwen3"),
    "nvidia_mistral_large": ("nvidia_mistral_large",),
}


def build_trio_reviewers(providers: list[Provider] | None = None) -> list[Reviewer]:
    """Ensambla el trío de revisores, uno por linaje distinto.

    Cada reviewer recibe un `InferenceHub` de UN solo proveedor (así `infer`
    llama solo a ese, sin fallback cruzado). Por cada slot del trío se prueba
    primero el proveedor primario del linaje; si no está en el pool, se usa el
    primer fallback DEL MISMO linaje que sí esté disponible (v2.0.5). Si
    ninguno de la lista está disponible, el slot queda vacío — el panel
    detectará la falta de diversidad y emitirá UNKNOWN aguas abajo (no se
    finge un trío incompleto).
    """
    pool = {p.name: p for p in (providers or DEFAULT_PROVIDERS)}
    out: list[Reviewer] = []
    for name in _TRIO_NAMES:
        lineage = _TRIO_LINEAGE_FALLBACKS.get(name, (name,))
        p = None
        for candidate in lineage:
            p = pool.get(candidate)
            if p is not None:
                break
        if p is None:
            continue
        out.append(LlmReviewer(p.name, p.name, InferenceHub(providers=[p]), p.level))
    return out


def _has_real_disagreement(evidence: Evidence) -> bool:
    """Hay desacuerdo sustantivo si el veredicto no es ya UNKNOWN y los checks
    de los reviewers NO son unánimes (algunos pasan, otros no) — eso indica
    que el trío no comparte lectura, señal real de que vale la pena otra
    ronda de debate. Consenso (todos pasan o todos fallan) no amerita otra
    ronda: ya está claro."""
    from atlas.core.verify import Verdict
    if evidence.verdict == Verdict.UNKNOWN:
        return False
    passed_count = sum(1 for c in evidence.checks if c.passed)
    failing_count = len(evidence.checks) - passed_count
    return passed_count > 0 and failing_count > 0


def _objections_summary(evidence: Evidence) -> str:
    """Resumen legible de los `detail` de los checks fallidos, para pasar como
    contexto adicional a la siguiente ronda. Prefijado con el marcador que
    reviewers/tests usan para detectar 'esto ya es una ronda de seguimiento'."""
    details = [c.detail for c in evidence.checks if not c.passed and c.detail]
    if not details:
        return ""
    joined = "\n".join(f"- {d}" for d in details)
    return f"[ronda-anterior] Objeciones de la ronda previa:\n{joined}"


def convene_for_decision(
    decision: str,
    context: str = "",
    *,
    difficulty: Difficulty,
    risk: str,
    irreversible: bool = False,
    reviewers: list[Reviewer] | None = None,
    synthesis_recorder: SynthesisRecorder | None = None,
    rounds: int = 1,
) -> Evidence | None:
    """Convoca el trío sobre una decisión, con gating y diversidad obligatoria.

    Devuelve `None` si el gating dice que NO escale (lo trivial-reversible no
    quema modelos). Si escala, corre el panel exigiendo 3 proveedores distintos;
    sin esa diversidad el panel devuelve `Verdict.UNKNOWN` (unknown > mentir).

    `rounds` (v2.1, opt-in): con `rounds=1` (default) es EXACTAMENTE el
    comportamiento anterior, una sola pasada. Con `rounds > 1`, si la primera
    pasada muestra desacuerdo real (`_has_real_disagreement`), se relanza el
    panel con el contexto original + un resumen de las objeciones previas,
    hasta agotar `rounds` o hasta que ya no haya objeciones nuevas (converge).

    Nunca cuelga: si CUALQUIER reviewer falla/lanza en una ronda intermedia,
    se corta ahí mismo y se sintetiza con la ÚLTIMA evidencia completa
    obtenida — jamás se espera indefinidamente ni se relanza la ronda fallida
    (preocupación señalada por Mistral en una deliberación en vivo sobre este
    mismo diseño).
    """
    if not should_convene(difficulty, risk, irreversible=irreversible):
        return None
    panel_reviewers = reviewers or build_trio_reviewers()
    panel = AdversarialPanel(panel_reviewers, min_providers=3)

    evidence = panel.verify(decision, context)
    round_context = context
    for _ in range(max(rounds, 1) - 1):
        if not _has_real_disagreement(evidence):
            break
        summary = _objections_summary(evidence)
        if not summary:
            break
        round_context = f"{context}\n\n{summary}"
        try:
            next_evidence = panel.verify(decision, round_context)
        except Exception:  # noqa: BLE001 — nunca cuelga: corta y sintetiza con lo que hay
            break
        if not _has_real_disagreement(next_evidence) or _objections_summary(next_evidence) == summary:
            # Converge (sin más objeciones nuevas) o ya no hay desacuerdo: esta
            # última pasada ya refleja el estado final, se conserva.
            evidence = next_evidence
            break
        evidence = next_evidence

    from atlas.core.verify import Verdict
    if synthesis_recorder is not None and evidence is not None and evidence.verdict != Verdict.UNKNOWN:
        record_synthesis(synthesis_recorder, decision, evidence)
    return evidence


class SynthesisRecorder(Protocol):
    """Sumidero inyectable para la síntesis del juez (destilación, v1 mínima).

    Mantenerlo como Protocol evita acoplar a la firma concreta del LessonStore;
    se cablea al recorder real (teacher_debate/LessonStore) cuando se valide
    (`wire-before-claim`: registrar lecciones ≠ garantizar que Atlas herede juicio).
    """

    def record(self, text: str) -> None: ...


class LessonSynthesisRecorder:
    """SynthesisRecorder que persiste en LessonStore via LessonPromoter."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def record(self, text: str) -> None:
        from atlas.core.lesson_store import LessonPromoter
        LessonPromoter(self._store).ingest_external(
            title=text[:80],
            detection_heuristic="Síntesis Cónclave",
            avoid_pattern=text,
            source_refs=("conclave:deliberation",),
            corroborated=True,
            reason="Veredicto trío",
        )


def record_synthesis(
    recorder: SynthesisRecorder, decision: str, evidence: Evidence
) -> None:
    """Registra el veredicto + razón legible de una deliberación. Side-effect barato."""
    reason = f" — {evidence.reason}" if evidence.reason else ""
    recorder.record(f"[{evidence.verdict.name}] {decision}{reason}")
