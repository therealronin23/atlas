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
    assert r.review("x").severity == Severity.MAJOR


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
    assert provs == {"gemini_free", "nvidia_kimi", "nvidia_mistral_large"}
