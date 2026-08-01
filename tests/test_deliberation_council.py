"""
TDD — Cónclave (deliberation_council): adaptador de deliberación multi-voz.

Reviewers concretos sobre proveedores de InferenceHub, ensamblados en un trío
de linajes distintos, con gating y veredicto honesto (PASS/FAIL/UNKNOWN).
"""

from __future__ import annotations

from atlas.core.adversarial_panel import Objection, Severity
from atlas.core.inference_hub import (
    InferenceLevel,
    InferenceRequest,
    InferenceResponse,
)


class _FakeHub:
    """Hub falso: devuelve un texto fijo, registra el prompt recibido."""

    def __init__(self, text: str, success: bool = True) -> None:
        self._text = text
        self._success = success
        self.last_request: InferenceRequest | None = None

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.last_request = request
        return InferenceResponse(
            text=self._text,
            provider="p",
            model="m",
            level=request.level,
            latency_ms=1,
            success=self._success,
        )


# ---------------------------------------------------------------------------
# B1 — LlmReviewer
# ---------------------------------------------------------------------------


def test_review_parses_severity_and_detail() -> None:
    from atlas.core.deliberation_council import LlmReviewer

    hub = _FakeHub("MAJOR\nAsume disponibilidad que no está probada.")
    r = LlmReviewer("kimi", "moonshot", hub, InferenceLevel.L2)
    obj = r.review("¿migrar a GraphQL?", context="200 endpoints")
    assert isinstance(obj, Objection)
    assert obj.severity == Severity.MAJOR
    assert "disponibilidad" in obj.detail
    assert obj.provider == "moonshot"


def test_review_unparseable_first_line_is_major_failclosed() -> None:
    from atlas.core.deliberation_council import LlmReviewer

    hub = _FakeHub("bla bla sin etiqueta")
    r = LlmReviewer("g", "google", hub, InferenceLevel.L1)
    obj = r.review("d")
    assert obj.severity is Severity.MAJOR
    assert obj.detail == "bla bla sin etiqueta"   # conserva contenido (antes: vacío)


def test_review_no_severity_keeps_full_text_as_detail() -> None:
    from atlas.core.deliberation_council import LlmReviewer

    # Kimi devuelve contenido real SIN severidad en 1a línea (bug reproducido en vivo).
    hub = _FakeHub("Esta decisión asume disponibilidad no probada.\ny encima ignora X.")
    r = LlmReviewer("kimi", "moonshot", hub, InferenceLevel.L2)
    obj = r.review("diff", "ctx")
    assert obj.severity is Severity.MAJOR  # fail-closed, sin cambio
    assert "disponibilidad no probada" in obj.detail  # NO se tira lines[0]
    assert "ignora X" in obj.detail


def test_review_bracketed_severity_in_first_line() -> None:
    from atlas.core.deliberation_council import LlmReviewer

    hub = _FakeHub("[MAJOR] rompe el contrato de tipos.")
    r = LlmReviewer("g", "google", hub, InferenceLevel.L1)
    obj = r.review("diff")
    assert obj.severity is Severity.MAJOR
    assert "rompe el contrato" in obj.detail


def test_review_negation_is_not_false_positive() -> None:
    from atlas.core.deliberation_council import LlmReviewer

    # "no es MAJOR" NO debe casar severidad (anclado a 1a línea, no scan global).
    hub = _FakeHub("no es MAJOR, pero hay un caso límite con NONE de los flujos.")
    r = LlmReviewer("m", "mistral", hub, InferenceLevel.L2)
    obj = r.review("diff")
    assert obj.severity is Severity.MAJOR          # default fail-closed
    assert "caso límite" in obj.detail             # texto completo conservado


def test_review_failed_inference_is_failclosed_major() -> None:
    # Una llamada fallida no puede contar como "sin objeción"; fail-closed a MAJOR.
    from atlas.core.deliberation_council import LlmReviewer

    hub = _FakeHub("", success=False)
    r = LlmReviewer("g", "google", hub, InferenceLevel.L1)
    assert r.review("x").severity == Severity.MAJOR


# ---------------------------------------------------------------------------
# B2 — build_trio_reviewers (2026-08-01: alias de build_council_reviewers,
# 5 asientos -- ver tests/test_council_five_roles.py para la cobertura nueva
# de roles/linajes. Lo que sigue aquí es lo que SIGUE siendo cierto del
# mecanismo de fallback, ahora sobre 5 asientos en vez de 3.)
# ---------------------------------------------------------------------------


def test_build_trio_has_five_distinct_providers() -> None:
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()
    assert len(council) == 5
    provs = {r.provider for r in council}
    # Zhipu (nvidia_glm) y Alibaba (groq_qwen3) ya NO comparten asiento --
    # cada rol tiene su propio linaje (ver COUNCIL_ROLES).
    assert provs == {
        "gemini_free", "nvidia_mistral_large", "nvidia_glm",
        "nvidia_llama_large", "groq_qwen3",
    }


# ---------------------------------------------------------------------------
# B3 — convene_for_decision (gating + panel + veredicto)
# ---------------------------------------------------------------------------


class _Rev:
    """Reviewer falso para tests de panel: severidad fija inyectada."""

    def __init__(self, pid: str, prov: str, sev: Severity) -> None:
        self._id, self._prov, self._sev = pid, prov, sev

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._prov

    def review(self, diff: str, context: str = "") -> Objection:
        return Objection(self._id, self._prov, self._sev, "obj")


def test_convene_returns_none_when_gating_says_skip() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.deliberation_council import convene_for_decision

    out = convene_for_decision(
        "renombrar variable", difficulty=Difficulty.MECHANICAL, risk="low", irreversible=False,
    )
    assert out is None


def test_convene_runs_panel_on_high_risk() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.verify import Verdict
    from atlas.core.deliberation_council import convene_for_decision

    trio = [
        _Rev("a", "p1", Severity.NONE),
        _Rev("b", "p2", Severity.NONE),
        _Rev("c", "p3", Severity.NONE),
    ]
    ev = convene_for_decision(
        "¿migrar a GraphQL?", difficulty=Difficulty.HARD, risk="high", reviewers=trio,
    )
    assert ev is not None and ev.verdict == Verdict.PASS


def test_convene_unknown_when_diversity_insufficient() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.verify import Verdict
    from atlas.core.deliberation_council import convene_for_decision

    # Dos revisores del MISMO provider → < 3 distintos → UNKNOWN.
    pair = [_Rev("a", "same", Severity.NONE), _Rev("b", "same", Severity.NONE)]
    ev = convene_for_decision(
        "x", difficulty=Difficulty.HARD, risk="high", reviewers=pair,
    )
    assert ev is not None and ev.verdict == Verdict.UNKNOWN


# ---------------------------------------------------------------------------
# B4 — record_synthesis (side-effect de destilación, recorder inyectable)
# ---------------------------------------------------------------------------


def test_record_synthesis_writes_verdict_and_reason() -> None:
    from atlas.core.verify import Evidence, Verdict
    from atlas.core.deliberation_council import record_synthesis

    class _Rec:
        def __init__(self) -> None:
            self.entries: list[str] = []

        def record(self, text: str) -> None:
            self.entries.append(text)

    rec = _Rec()
    ev = Evidence(verdict=Verdict.FAIL, reason="Kimi: asume X falso")
    record_synthesis(rec, "¿migrar a GraphQL?", ev)
    assert len(rec.entries) == 1
    assert "FAIL" in rec.entries[0] and "GraphQL" in rec.entries[0]


def test_synthesis_persists_to_lesson_store(tmp_path):
    from atlas.core.lesson_store import LessonStore
    from atlas.core.deliberation_council import LessonSynthesisRecorder, record_synthesis
    from atlas.core.verify import Evidence, Verdict

    store = LessonStore(tmp_path / "lessons")
    recorder = LessonSynthesisRecorder(store)
    ev = Evidence(verdict=Verdict.FAIL, reason="eval() es inseguro")
    record_synthesis(recorder, "usar eval() para parsear config", ev)
    lessons = store.all()
    assert len(lessons) == 1
    assert "FAIL" in lessons[0].avoid_pattern


# ---------------------------------------------------------------------------
# v2.0.5 — fallback por linaje en build_trio_reviewers
# ---------------------------------------------------------------------------


def test_build_trio_uses_lineage_fallback_when_primary_missing():
    """Si falta gemini_free en el pool mas groq_llama_70b SÍ está, el asiento
    Contrarian usa groq_llama_70b (mismo linaje) — nunca cruza a otro linaje.

    Con este pool constreñido, DOS asientos (Contrarian y Outsider) caen al
    MISMO fallback groq_llama_70b -- degradación honesta, no un error: el
    panel dedupe por proveedor que de verdad respondió, aguas abajo."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"groq_llama_70b", "nvidia_glm", "nvidia_mistral_large"}
    ]
    council = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in council}
    assert "groq_llama_70b" in provs
    assert "gemini_free" not in provs
    assert "nvidia_glm" in provs
    assert "nvidia_mistral_large" in provs
    # Executor (Alibaba: groq_qwen3/ollama_local) no tiene NADA en este pool
    # -> asiento vacío. Contrarian y Outsider comparten groq_llama_70b.
    assert len(council) == 4
    assert len(provs) == 3


def test_build_trio_slot_empty_when_no_fallback_available():
    """Si el pool no tiene NI el primario NI el fallback de un linaje, el
    slot queda vacío (comportamiento ya existente, no se inventa uno)."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"gemini_free", "nvidia_glm"}
    ]
    trio = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in trio}
    assert "nvidia_mistral_large" not in provs
    assert len(trio) == 2


def test_build_trio_eu_uses_openrouter_mistral_fallback_when_nvidia_missing():
    """Hueco EU cerrado 2026-07-24: nvidia_mistral_large (NIM) da 410 Gone
    (EOL); openrouter_mistral_large (mistralai/mistral-large-2512, prove-it
    en vivo real contra OpenRouter, provider real 'Mistral') es el fallback
    del MISMO linaje EU -- nunca se cruza a otro."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"gemini_free", "nvidia_glm", "openrouter_mistral_large"}
    ]
    trio = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in trio}
    assert "openrouter_mistral_large" in provs
    assert "nvidia_mistral_large" not in provs
    assert len(trio) == 3


def test_build_trio_prefers_primary_over_fallback_when_both_available():
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()  # pool completo por defecto
    provs = {r.provider for r in council}
    # 2026-08-01: 5 asientos, uno por linaje -- ver COUNCIL_ROLES.
    assert provs == {
        "gemini_free", "nvidia_mistral_large", "nvidia_glm",
        "nvidia_llama_large", "groq_qwen3",
    }


def test_build_trio_hub_carries_full_lineage_for_hot_call_fallback():
    """Fix 2026-07-24: el hub de cada reviewer lleva la lista ORDENADA de
    proveedores del MISMO linaje (no solo el primario), para que InferenceHub
    casque en caliente si el primario tiene key pero su llamada falla
    (resp.success=False). Antes solo caía a fallback si faltaba la key en el pool,
    dejando el slot muerto ante un proveedor keyed-pero-caído (Mistral EU 410,
    NVIDIA rate-limit). La etiqueta `.provider` sigue siendo el primario (la
    diversidad del trío se mide por linaje, no por vendor de hosting).

    2026-08-01: Zhipu (nvidia_glm) y Alibaba (groq_qwen3) ya no comparten
    asiento -- cada uno tiene su propio rol (Expansionist / Executor). El
    mecanismo que este test verifica (lista completa de linaje en el hub) no
    cambia."""
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()  # pool completo
    us = next(r for r in council if r.provider == "gemini_free")
    zhipu = next(r for r in council if r.provider == "nvidia_glm")
    alibaba = next(r for r in council if r.provider == "groq_qwen3")
    assert [p.name for p in us._hub._providers] == ["gemini_free", "groq_llama_70b"]
    assert [p.name for p in zhipu._hub._providers] == ["nvidia_glm"]
    assert [p.name for p in alibaba._hub._providers] == ["groq_qwen3", "ollama_local"]


def test_lineage_fallback_is_actually_reachable_when_levels_differ(monkeypatch):
    """2026-07-30 — el fallback de linaje estaba CONSTRUIDO pero INALCANZABLE
    en 2 de los 3 asientos. Los tests previos verifican qué proveedores lleva
    el hub (construcción); ninguno verificaba que se llegue a ellos al LLAMAR.

    `InferenceHub._walk_chain` filtra candidatos con `p.level == request.level`
    (filtro DURO; la única escapatoria entre niveles es L1->L0). Y
    `build_trio_reviewers` pasa `primary.level` como nivel de la petición. Con
    los niveles reales del catálogo (estado 2026-07-30, antes del reorden CN):

        US  gemini_free           L0  ->  groq_llama_70b            L1   INALCANZABLE
        CN  nvidia_glm            L2  ->  groq_qwen3                L0   INALCANZABLE
        EU  nvidia_mistral_large  L2  ->  openrouter_mistral_large  L2   ok

    Medido en vivo el mismo día: el asiento CN tardó 123.0s y devolvió
    `reachable=False` — `nvidia_glm` se cuelga y `groq_qwen3` NUNCA se intentó.
    Es la causa de que el Cónclave no alcanzara quórum (2/3) pese a tener el
    fallback "configurado".

    2026-07-31: el linaje CN se invirtió (ver `_TRIO_LINEAGE_FALLBACKS`), así
    que en producción ya no ejerce este camino -- groq_qwen3 (ahora primario)
    responde directo. El asiento US SÍ sigue siendo asimétrico
    (gemini_free L0 -> groq_llama_70b L1) y es el que este test usa ahora
    para seguir probando el mecanismo general, no un caso ya resuelto.
    """
    import litellm  # type: ignore

    from atlas.core.deliberation_council import build_trio_reviewers

    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    # build_trio_reviewers construye hubs en modo "auto", que dentro de pytest
    # resuelve a stub: sin esto no se llamaría a NINGÚN proveedor y el test
    # verificaría el stub, no el enrutado real por nivel que es lo que falla.
    monkeypatch.setenv("ATLAS_INFERENCE_MODE", "live")

    seen: list[str] = []

    def fake_completion(**kwargs):
        model = kwargs.get("model", "")
        seen.append(model)
        if "gemini" in model:  # el primario US se cae
            raise RuntimeError("boom: primario del linaje caído")
        msg = type("M", (), {"content": "MINOR\nel fallback del linaje contestó"})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice], "usage": None})()

    monkeypatch.setattr(litellm, "completion", fake_completion)

    us = next(r for r in build_trio_reviewers() if r.provider == "gemini_free")
    obj = us.review("¿decisión de prueba?", "")

    assert any("llama" in m for m in seen), (
        f"el fallback del MISMO linaje debe intentarse aunque su nivel difiera "
        f"del primario; modelos realmente llamados: {seen}"
    )
    assert obj.reachable is True, (
        "un asiento cuyo fallback de linaje contesta NO es un asiento muerto"
    )
    assert obj.provider == "gemini_free", (
        "la etiqueta sigue siendo el primario: la diversidad se mide por linaje"
    )


# v2.1 (rounds>1 por desacuerdo bruto) fue REEMPLAZADO 2026-08-01 por rondas
# por PELIGROSIDAD (pedido del operador): el parámetro se renombró
# `rounds` -> `max_rounds`, el disparador pasó de "hay desacuerdo" a "el
# veredicto es FAIL" (supera `AdversarialPanel.block_at`), y la ronda extra
# ahora es una revisión ANÓNIMA entre pares, no un resumen con el marcador
# `[ronda-anterior]`. Cobertura completa en tests/test_council_danger_rounds.py.
# ---------------------------------------------------------------------------
# (bloque histórico retirado — ver git log para la versión rounds>1 previa)
# ---------------------------------------------------------------------------
