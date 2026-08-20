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


def test_build_trio_has_four_distinct_providers_due_to_fallbacks() -> None:
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()
    assert len(council) == 4  # 5 papeles declarados, 4 con linaje vivo
    provs = {r.provider for r in council}
    # 2026-08-05: `nvidia_glm` (único Zhipu) quedó DOWN tras días de smoke
    # muerto, así que su asiento no se monta. El conjunto es el de los linajes
    # VIVOS, no una lista congelada.
    assert provs == {
        "groq_gpt_oss_120b", "openrouter_mistral_large",
        "groq_qwen3", "openrouter_hermes4_70b",
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
    """Si falta groq_qwen3 en el pool mas ollama_local SÍ está, el asiento
    Executor usa ollama_local (mismo linaje)."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"ollama_local", "nvidia_glm", "openrouter_mistral_large", "groq_gpt_oss_120b", "openrouter_hermes4_70b"}
    ]
    council = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in council}
    assert "ollama_local" in provs
    assert "groq_qwen3" not in provs
    assert len(council) == 4  # nvidia_glm sigue DOWN, su asiento no se monta

def test_build_trio_slot_empty_when_no_fallback_available():
    """Si el pool no tiene NI el primario NI el fallback de un linaje, el
    slot queda vacío."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"openrouter_mistral_large", "nvidia_glm"}
    ]
    trio = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in trio}
    assert "groq_gpt_oss_120b" not in provs
    # openrouter_mistral_large monta su asiento; nvidia_glm está DOWN.
    assert len(trio) == 1

def test_build_trio_prefers_primary_over_fallback_when_both_available():
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()  # pool completo por defecto
    provs = {r.provider for r in council}
    # 2026-08-01: 5 asientos, uno por linaje
    # 2026-08-05: `nvidia_glm` (único Zhipu) quedó DOWN tras días de smoke
    # muerto, así que su asiento no se monta. El conjunto es el de los linajes
    # VIVOS, no una lista congelada.
    assert provs == {
        "groq_gpt_oss_120b", "openrouter_mistral_large",
        "groq_qwen3", "openrouter_hermes4_70b",
    }

def test_build_trio_hub_carries_full_lineage_for_hot_call_fallback():
    """Fix 2026-07-24: el hub de cada reviewer lleva la lista ORDENADA de
    proveedores del MISMO linaje (no solo el primario)."""
    from atlas.core.deliberation_council import build_trio_reviewers

    council = build_trio_reviewers()  # pool completo
    alibaba = next(r for r in council if r.reviewer_id == "executor:groq_qwen3")
    assert [p.name for p in alibaba._hub._providers] == ["groq_qwen3", "ollama_local"]

def test_lineage_fallback_is_actually_reachable_when_levels_differ(monkeypatch):
    """Prueba que el fallback de linaje es alcanzable."""
    import litellm  # type: ignore
    from atlas.core.deliberation_council import build_trio_reviewers

    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("ATLAS_INFERENCE_MODE", "live")

    seen: list[str] = []

    def fake_completion(**kwargs):
        model = kwargs.get("model", "")
        seen.append(model)
        if "groq/qwen" in model:  # el primario cae
            raise RuntimeError("boom")
        msg = type("M", (), {"content": "MINOR\nel fallback del linaje contestó"})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice], "usage": None})()

    monkeypatch.setattr(litellm, "completion", fake_completion)

    executor = next(r for r in build_trio_reviewers() if r.reviewer_id == "executor:groq_qwen3")
    obj = executor.review("¿decisión de prueba?", "")

    assert obj.reachable is True
    assert obj.provider == "groq_qwen3", "la etiqueta sigue siendo el primario"

# v2.1 (rounds>1 por desacuerdo bruto) fue REEMPLAZADO 2026-08-01...
# ---------------------------------------------------------------------------
