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

import re
from dataclasses import dataclass
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
    ProviderStatus,
)
from atlas.core.verify import Evidence
from atlas.router.cascade import Difficulty

_HOSTILE_PROMPT = (
    "Eres un revisor hostil. Ataca esta decisión: ¿qué rompe, qué asume falso, "
    "qué caso límite ignora? Responde en la PRIMERA línea SOLO con una de: "
    "NONE MINOR MAJOR BLOCKING. En las siguientes líneas, la objeción concreta.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)

# 2026-08-01: el operador trajo dos repos (aiwithremy/claude-skills-llm-council,
# gcpdev/llm-council-skill). El primero reveló el hallazgo que reordena este
# módulo: sus "5 voces" no son 5 modelos, son 5 ROLES de pensamiento con una
# ronda de revisión anónima entre pares. `_HOSTILE_PROMPT` de arriba ES el
# Contrarian -- y corríamos ese único papel en los tres asientos. Explica la
# patología medida el 31-jul: Gemini calificó BLOCKING un cambio de timeout de
# 30s a 60s porque el panel entero sólo sabía "buscar el fallo fatal", nunca
# "¿qué oportunidad se pierde?" ni "¿esto es viable de implementar?".
#
# El prompt hostil NO se ablanda -- el operador fue explícito: "el Cónclave
# estuvo bien hasta ahora". Se le añaden los otros cuatro roles.
_FIRST_PRINCIPLES_PROMPT = (
    "Eres un pensador de primeros principios. Cuestiona las asunciones de esta "
    "decisión: ¿qué se da por sentado que podría ser falso? ¿Qué cambia si el "
    "problema se replantea desde cero, ignorando cómo se ha hecho hasta ahora? "
    "Responde en la PRIMERA línea SOLO con una de: NONE MINOR MAJOR BLOCKING. "
    "En las siguientes líneas, la asunción cuestionada y por qué importa.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)
_EXPANSIONIST_PROMPT = (
    "Eres un expansionista. Busca la oportunidad adyacente que esta decisión "
    "ignora, y si ignorarla es en sí un riesgo real -- dejar pasar algo que "
    "evitaría un problema mayor más adelante. No inventes upside donde no lo "
    "hay: NONE es una respuesta válida y honesta. Responde en la PRIMERA "
    "línea SOLO con una de: NONE MINOR MAJOR BLOCKING. En las siguientes "
    "líneas, la oportunidad perdida concreta.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)
_OUTSIDER_PROMPT = (
    "Eres alguien de fuera de este dominio, sin experiencia previa en él. "
    "Mira esta decisión con ojos nuevos, sin dar nada por sabido: ¿qué "
    "resultaría extraño, sobrecomplicado o innecesario para quien no conoce "
    "el contexto? Responde en la PRIMERA línea SOLO con una de: NONE MINOR "
    "MAJOR BLOCKING. En las siguientes líneas, la objeción concreta.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)
_EXECUTOR_PROMPT = (
    "Eres el ejecutor. Sólo te importa la viabilidad práctica: ¿se puede "
    "implementar tal cual está descrita? ¿Qué primer paso concreto falta, es "
    "ambiguo, o depende de algo que no está garantizado? Responde en la "
    "PRIMERA línea SOLO con una de: NONE MINOR MAJOR BLOCKING. En las "
    "siguientes líneas, el obstáculo de implementación concreto.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)

_SEVERITIES = {s.name: s for s in Severity}

# 2026-07-31: el default de `InferenceRequest` (1024) AHOGA a los modelos de
# razonamiento, que gastan presupuesto de salida pensando. Medido en vivo con
# gemini-2.5-flash y el mismo prompt hostil: 1024 -> 153 chars (una frase
# cortada); 4096 -> 510 chars (tres objeciones completas). El fallo era
# traicionero porque el insulto va PRIMERO y el análisis después: la
# truncación se comía la sustancia y dejaba intacta la agresividad, así que
# parecía que el modelo sólo sabía insultar. En el Cónclave real de ese día un
# voto BLOCKING se emitió sobre un fragmento y el panel lo contó como voz
# completa.
_REVIEW_MAX_TOKENS = 4096

# Modelos de razonamiento (Qwen, DeepSeek...) emiten su cadena de pensamiento
# antes de responder. Como la severidad se ancla a la PRIMERA línea, esa línea
# era `<think>` y el parseo caía al fail-closed MAJOR, DESCARTANDO la severidad
# real del modelo. No es cosmética: el panel registraba una severidad distinta
# de la que la voz había dado.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Quita bloques `<think>...</think>` cerrados.

    Un bloque SIN cerrar (el modelo se quedó sin presupuesto a mitad) se
    conserva tal cual: preferible un detalle ruidoso a devolver vacío y perder
    la única señal que esa voz llegó a emitir."""
    return _THINK_BLOCK.sub("", text).strip()


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
        levels: tuple[InferenceLevel, ...] | None = None,
        prompt: str = _HOSTILE_PROMPT,
    ) -> None:
        self._id = reviewer_id
        self._provider = provider
        self._hub = hub
        self._level = level
        self._prompt = prompt
        # 2026-07-30: `InferenceHub._walk_chain` filtra candidatos con
        # `p.level == request.level` (filtro DURO; la única escapatoria entre
        # niveles es L1->L0). Pedir siempre `primary.level` dejaba INALCANZABLE
        # cualquier fallback del mismo linaje declarado en otro nivel -- 2 de
        # los 3 asientos del trío (US L0->L1, CN L2->L0). Medido en vivo: el
        # asiento CN tardó 123s y devolvió reachable=False porque `nvidia_glm`
        # se cuelga y `groq_qwen3` NUNCA se intentó. Recorrer los niveles del
        # propio linaje, en orden, arregla la alcanzabilidad sin tocar el
        # enrutado del hub para el resto de callers.
        self._levels: tuple[InferenceLevel, ...] = levels or (level,)

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._provider

    def review(self, diff: str, context: str = "") -> Objection:
        prompt = self._prompt.format(diff=diff, context=context)
        resp = None
        for level in self._levels:
            resp = self._hub.infer(
                InferenceRequest(
                    prompt=prompt, level=level, max_tokens=_REVIEW_MAX_TOKENS
                )
            )
            if resp.success and resp.text.strip():
                break
        if resp is None or not resp.success or not resp.text.strip():
            return Objection(
                self._id, self._provider, Severity.MAJOR,
                "revisión no disponible (fail-closed)",
                reachable=False,
            )
        cleaned = _strip_thinking(resp.text)
        lines = cleaned.splitlines()
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


@dataclass(frozen=True)
class CouncilSeat:
    """Un asiento = un ROL de pensamiento sobre un LINAJE de preentrenamiento.

    Los dos ejes son ortogonales (hallazgo 2026-08-01, ver comentario de los
    prompts arriba): el rol decide QUÉ pregunta se hace, el linaje decide
    QUIÉN diverge de verdad. `lineage` es la lista ORDENADA de proveedores del
    MISMO linaje (primario primero) — mismo contrato que el viejo
    `_TRIO_LINEAGE_FALLBACKS`, nunca se cruza a otro linaje.
    """

    role: str
    prompt: str
    lineage: tuple[str, ...]


# Cinco roles (aiwithremy/claude-skills-llm-council) × cinco linajes
# (nuestro eje histórico), un rol por linaje distinto -- cubre AMBOS ejes a
# la vez, que es más que cualquiera de los dos diseños por separado.
#
# Defecto corregido al separar: el viejo `_TRIO_LINEAGE_FALLBACKS["nvidia_glm"]
# = ("groq_qwen3", "nvidia_glm")` ponía a Qwen (Alibaba) de PRIMARIO del
# asiento "CN" y a GLM (Zhipu) de fallback -- dos laboratorios distintos
# cruzados dentro de un único slot, justo lo que "nunca cruzar de linaje"
# prohibía. Con 5 roles cada uno tiene su propio asiento: Zhipu y Alibaba ya
# no comparten slot.
#
# nvidia_glm (Expansionist) sigue siendo la única opción de linaje Zhipu en el
# catálogo, y sigue sin fallback: se cuelga a veces (medido dos veces,
# 2026-07-30). Con el panel PARALELIZADO (ver adversarial_panel.py) un cuelgue
# de este asiento ya no suma tiempo al de los demás -- acota la ronda a
# INFER_REQUEST_TIMEOUT_S, no la multiplica por asiento. Riesgo conocido y
# aceptado, no arreglado aquí (fuera de alcance de este rediseño).
COUNCIL_ROLES: tuple[CouncilSeat, ...] = (
    CouncilSeat("contrarian", _HOSTILE_PROMPT, ("groq_llama_70b",)),
    CouncilSeat(
        "first_principles", _FIRST_PRINCIPLES_PROMPT,
        ("openrouter_mistral_large", "nvidia_mistral_medium"),
    ),
    CouncilSeat("expansionist", _EXPANSIONIST_PROMPT, ("nvidia_glm",)),
    CouncilSeat("outsider", _OUTSIDER_PROMPT, ("openrouter_hermes4_70b", "openrouter_nemotron")),
    CouncilSeat("executor", _EXECUTOR_PROMPT, ("groq_qwen3", "ollama_local")),
)


def build_council_reviewers(providers: list[Provider] | None = None) -> list[Reviewer]:
    """Ensambla el Cónclave: 5 asientos, un rol por linaje distinto.

    Por cada asiento se prueba primero el proveedor primario de su linaje; si
    no está en el pool, el primer fallback DEL MISMO linaje que sí esté
    disponible (mismo contrato v2.0.5 que el viejo trío). Si ninguno de la
    lista está disponible, el asiento queda vacío — el panel detecta la falta
    de diversidad y emite UNKNOWN aguas abajo (no se finge un panel completo).

    `reviewer_id` lleva el ROL, no sólo el proveedor (`"{role}:{provider}"`):
    con 5 papeles distintos, logs y síntesis necesitan saber QUÉ pregunta
    hizo cada objeción, no sólo quién la respondió.
    """
    pool = {p.name: p for p in (providers or DEFAULT_PROVIDERS)}
    out: list[Reviewer] = []
    for seat in COUNCIL_ROLES:
        # Toda la lista de linaje disponible, EN ORDEN (primario primero). El hub
        # multi-proveedor de InferenceHub casca en caliente: si el primario tiene
        # key pero su llamada falla (resp.success=False -- Mistral EU 410, NVIDIA
        # rate-limit), pasa al siguiente DEL MISMO linaje. Nunca cruza de linaje
        # (romper la ortogonalidad anula la señal de desacuerdo). La etiqueta
        # `.provider` sigue siendo el primario: la diversidad se mide por
        # linaje, no por vendor de hosting.
        # Se excluyen los proveedores marcados DOWN. Sin esto, un asiento
        # sentado sobre un proveedor caído no daba UNKNOWN rápido: colgaba la
        # deliberación 30-120s por ronda para acabar devolviendo
        # `reachable=False` — medido el 2026-08-05, y era la causa de que el
        # Cónclave tardara minutos en no decir nada. Un asiento que no existe
        # es MEJOR que uno que no contesta: el panel ya sabe emitir UNKNOWN por
        # falta de linajes, y lo hace en segundos.
        available = [
            pool[c] for c in seat.lineage
            if c in pool and pool[c].status is not ProviderStatus.DOWN
        ]
        if not available:
            continue
        primary = available[0]
        # Niveles del linaje EN ORDEN, sin repetir: el reviewer los recorre
        # para que un fallback declarado en otro nivel siga siendo alcanzable
        # (ver comentario en LlmReviewer.__init__).
        levels: tuple[InferenceLevel, ...] = tuple(
            dict.fromkeys(p.level for p in available)
        )
        out.append(
            LlmReviewer(
                f"{seat.role}:{primary.name}",
                primary.name,
                InferenceHub(providers=available),
                primary.level,
                levels=levels,
                prompt=seat.prompt,
            )
        )
    return out


# Alias retrocompatible: orchestrator.py, atlas_coder.py, code_cycle.py y 3
# scripts (council_smoke, council_adr077_design_review,
# council_mcp_auto_adopt_adr076) llaman a `build_trio_reviewers()`. Con el
# alias heredan las 5 voces sin tocar cada call-site uno a uno. El nombre es
# ya un desajuste (construye 5, no 3); se conserva para no romper 7+ sitios
# por un rename cosmético -- `build_council_reviewers` es el nombre real
# para código nuevo.
build_trio_reviewers = build_council_reviewers


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


# El umbral de peligrosidad YA EXISTE: `AdversarialPanel.block_at`
# (Severity.MAJOR por defecto). `Evidence.verdict == FAIL` es EXACTAMENTE "una
# objeción alcanzable superó ese umbral" (ver `verify()`, `blocking` no
# vacío) -- no se inventa una escala nueva para las rondas por peligrosidad.
#
# Con 5 asientos, "todos deben responder" (min_providers=5) haría el panel
# frágil ante un único asiento flaky (nvidia_glm se cuelga a veces, medido).
# El piso se mantiene en 3 -- el mismo mínimo que ya funcionaba con el trío,
# ahora como degradación honesta sobre 5 en vez de un requisito de 5-de-5.
MIN_REACHABLE_LINEAGES = 3

# Decisión del operador (2026-08-01): tope duro de 4 rondas. Agotadas sin
# bajar del umbral de peligrosidad, se para y escala al humano con las
# objeciones vivas -- fail-closed, "sin acuerdo no se actúa".
MAX_COUNCIL_ROUNDS = 4

_PEER_REVIEW_HEADER = (
    "[revisión-anónima] Las siguientes son las respuestas de OTRAS voces del "
    "panel a esta misma decisión, SIN identificar autor ni proveedor. Para "
    "cada una: ¿cuál es la más fuerte? ¿cuál tiene el mayor punto ciego? "
    "¿qué se les escapa a TODAS? Después, en tu propia respuesta, proponed "
    "la variante MENOS peligrosa de la decisión que conserve el objetivo "
    "original -- no os limitéis a repetir la objeción de la ronda anterior."
)


def _anonymize_for_peer_review(evidence: Evidence) -> str:
    """Las 5 respuestas crudas, despojadas de rol y proveedor.

    Reutiliza `evidence.checks[i].detail` (ya trae `[SEVERIDAD] texto`), pero
    NUNCA `checks[i].name` (que es `f"{role}:{provider}@{provider}"`) — es
    justo lo que hay que ocultar para que la revisión entre pares sea
    honesta y no una defensa de la propia respuesta.
    """
    lines = [_PEER_REVIEW_HEADER]
    for i, check in enumerate(evidence.checks, start=1):
        lines.append(f"Respuesta {i}: {check.detail}")
    return "\n".join(lines)


def convene_for_decision(
    decision: str,
    context: str = "",
    *,
    difficulty: Difficulty,
    risk: str,
    irreversible: bool = False,
    reviewers: list[Reviewer] | None = None,
    synthesis_recorder: SynthesisRecorder | None = None,
    max_rounds: int = MAX_COUNCIL_ROUNDS,
) -> Evidence | None:
    """Convoca el Cónclave (5 asientos) con gating, diversidad y RONDAS POR
    PELIGROSIDAD (2026-08-01, reemplaza el viejo bucle por desacuerdo bruto).

    Devuelve `None` si el gating dice que NO escale (lo trivial-reversible no
    quema modelos). Si escala, corre el panel exigiendo `MIN_REACHABLE_LINEAGES`
    proveedores distintos; sin esa diversidad el panel devuelve
    `Verdict.UNKNOWN` (unknown > mentir).

    El bucle de rondas:
    - Si NADA supera el umbral de peligrosidad (`verdict != FAIL`) tras la 1ª
      ronda, se PARA ahí — barato para lo seguro, ni una llamada de más.
    - Si SÍ lo supera y quedan rondas, se concede una ronda de REVISIÓN
      ANÓNIMA ENTRE PARES: cada asiento recibe las 5 respuestas sin rol ni
      proveedor y se le pide la variante MENOS peligrosa que conserve el
      objetivo — no repetir el ataque.
    - Converge (para) en cuanto el veredicto deja de ser FAIL, o cuando dos
      rondas seguidas producen exactamente el mismo resumen (no hay nada
      nuevo que decir).
    - Tope duro `max_rounds` (4 por decisión del operador): agotado sin
      converger, se PARA con el último veredicto — que sigue siendo FAIL, la
      señal ya establecida de "escala al humano" en este repo. Nunca se
      relaja a PASS sólo porque se acabó el presupuesto de rondas.

    Nunca cuelga: si CUALQUIER reviewer falla/lanza en una ronda intermedia,
    se corta ahí mismo y se sintetiza con la ÚLTIMA evidencia completa
    obtenida — jamás se espera indefinidamente ni se relanza la ronda fallida
    (preocupación señalada por Mistral en una deliberación en vivo sobre este
    mismo diseño).
    """
    from atlas.core.verify import Verdict

    if not should_convene(difficulty, risk, irreversible=irreversible):
        return None
    panel_reviewers = reviewers or build_trio_reviewers()
    panel = AdversarialPanel(panel_reviewers, min_providers=MIN_REACHABLE_LINEAGES)

    evidence = panel.verify(decision, context)
    previous_summary = _objections_summary(evidence)
    for _ in range(max(max_rounds, 1) - 1):
        if evidence.verdict != Verdict.FAIL:
            # Bajo el umbral de peligrosidad (o UNKNOWN por diversidad, que
            # otra ronda no arregla): no hay nada que mitigar. Para aquí.
            break
        round_context = f"{context}\n\n{_anonymize_for_peer_review(evidence)}"
        try:
            next_evidence = panel.verify(decision, round_context)
        except Exception:  # noqa: BLE001 — nunca cuelga: corta y sintetiza con lo que hay
            break
        next_summary = _objections_summary(next_evidence)
        evidence = next_evidence
        if evidence.verdict != Verdict.FAIL or next_summary == previous_summary:
            # Ya no es peligroso, o converge (nada nuevo que decir): esta
            # última pasada ya refleja el estado final.
            break
        previous_summary = next_summary

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
