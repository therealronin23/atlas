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
# B2 — build_trio_reviewers
# ---------------------------------------------------------------------------


def test_build_trio_has_three_distinct_providers() -> None:
    from atlas.core.deliberation_council import build_trio_reviewers

    trio = build_trio_reviewers()
    assert len(trio) == 3
    provs = {r.provider for r in trio}
    assert provs == {"gemini_free", "nvidia_glm", "nvidia_mistral_large"}


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
    """Si falta gemini_free en el pool mas groq_llama_70b SÍ está, el slot US
    usa groq_llama_70b (mismo linaje) — nunca cruza a otro linaje."""
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    pool = [
        p for p in DEFAULT_PROVIDERS
        if p.name in {"groq_llama_70b", "nvidia_glm", "nvidia_mistral_large"}
    ]
    trio = build_trio_reviewers(providers=pool)
    provs = {r.provider for r in trio}
    assert "groq_llama_70b" in provs
    assert "gemini_free" not in provs
    assert "nvidia_glm" in provs
    assert "nvidia_mistral_large" in provs
    assert len(trio) == 3


def test_build_trio_slot_empty_when_no_fallback_available():
    """EU (nvidia_mistral_large) no tiene fallback no-NIM vivo confirmado — si
    falta, el slot queda vacío (comportamiento ya existente, no se inventa uno)."""
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


def test_build_trio_prefers_primary_over_fallback_when_both_available():
    from atlas.core.deliberation_council import build_trio_reviewers
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    trio = build_trio_reviewers()  # pool completo por defecto
    provs = {r.provider for r in trio}
    assert provs == {"gemini_free", "nvidia_glm", "nvidia_mistral_large"}


# ---------------------------------------------------------------------------
# v2.1 — debate por rondas (opt-in, rounds>1)
# ---------------------------------------------------------------------------


class _RoundAwareRev:
    """Reviewer falso: severidad depende de si el `context` recibido ya
    contiene el resumen de objeciones de una ronda previa (heurística: busca
    un marcador fijo). Simula "converge en la 2a ronda"."""

    MARKER = "[ronda-anterior]"

    def __init__(
        self, pid: str, prov: str, first_round_sev: Severity, later_round_sev: Severity,
    ) -> None:
        self._id, self._prov = pid, prov
        self._first = first_round_sev
        self._later = later_round_sev
        self.calls: list[str] = []

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._prov

    def review(self, diff: str, context: str = "") -> Objection:
        self.calls.append(context)
        sev = self._later if self.MARKER in context else self._first
        return Objection(self._id, self._prov, sev, "obj ronda")


def test_convene_with_rounds_runs_second_pass_on_disagreement():
    from atlas.router.cascade import Difficulty
    from atlas.core.verify import Verdict
    from atlas.core.deliberation_council import convene_for_decision

    trio = [
        _RoundAwareRev("a", "p1", Severity.MAJOR, Severity.NONE),
        _RoundAwareRev("b", "p2", Severity.NONE, Severity.NONE),
        _RoundAwareRev("c", "p3", Severity.NONE, Severity.NONE),
    ]
    ev = convene_for_decision(
        "¿migrar a GraphQL?", difficulty=Difficulty.HARD, risk="high",
        reviewers=trio, rounds=2,  # type: ignore[arg-type]
    )
    assert ev is not None and ev.verdict == Verdict.PASS
    # cada reviewer llamado 2 veces (ronda 1 desacuerdo -> ronda 2 converge)
    assert all(len(r.calls) == 2 for r in trio)
    # la 2a llamada incluyó el resumen de objeciones de la 1a ronda
    assert any(_RoundAwareRev.MARKER in call for r in trio for call in r.calls[1:])


def test_convene_rounds_default_is_single_pass_backward_compatible() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.deliberation_council import convene_for_decision

    trio = [
        _RoundAwareRev("a", "p1", Severity.MAJOR, Severity.NONE),
        _RoundAwareRev("b", "p2", Severity.NONE, Severity.NONE),
        _RoundAwareRev("c", "p3", Severity.NONE, Severity.NONE),
    ]
    convene_for_decision(
        "x", difficulty=Difficulty.HARD, risk="high", reviewers=trio,  # type: ignore[arg-type]
    )  # rounds=1 (default)
    assert all(len(r.calls) == 1 for r in trio)


class _FailMidRoundRev:
    """Reviewer que responde bien en la ronda 1 pero lanza excepción en la
    ronda 2 (simula proveedor caído a mitad de una ronda intermedia)."""

    def __init__(self, pid: str, prov: str, fail_on_round: int) -> None:
        self._id, self._prov = pid, prov
        self._fail_on_round = fail_on_round
        self.calls = 0

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._prov

    def review(self, diff: str, context: str = "") -> Objection:
        self.calls += 1
        if self.calls == self._fail_on_round:
            raise RuntimeError("proveedor caído")
        return Objection(self._id, self._prov, Severity.MAJOR, "obj")


def test_convene_rounds_never_hangs_on_mid_round_failure() -> None:
    """Si un reviewer falla en una ronda intermedia, corta ahí y sintetiza con
    lo que hay hasta esa ronda — nunca espera indefinidamente ni relanza."""
    from atlas.router.cascade import Difficulty
    from atlas.core.deliberation_council import convene_for_decision

    trio = [
        _FailMidRoundRev("a", "p1", fail_on_round=2),
        _RoundAwareRev("b", "p2", Severity.MAJOR, Severity.NONE),
        _RoundAwareRev("c", "p3", Severity.NONE, Severity.NONE),
    ]
    # No debe lanzar ni colgarse; debe devolver evidencia sintetizada con la
    # última ronda completa disponible (ronda 1, ya que la 2 falló a mitad).
    ev = convene_for_decision(
        "x", difficulty=Difficulty.HARD, risk="high", reviewers=trio, rounds=3,  # type: ignore[arg-type]
    )
    assert ev is not None
    # el reviewer que falla se intentó exactamente en la ronda donde falla, no más
    assert trio[0].calls == 2  # type: ignore[attr-defined]
