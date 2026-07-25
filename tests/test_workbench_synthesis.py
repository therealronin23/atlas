"""Síntesis Gemini de la mesa de trabajo (diseño 2026-07-25, ver memoria
trunk-plan-cooperation-design). Proveedor dedicado (gemini_free) sin
fallback a la cadena de pago; fail-soft en cada punto -- nunca debe poder
romper el hook de prompts que lo invoca."""

from __future__ import annotations

from typing import Any

from atlas.mcp.workbench_synthesis import (
    build_synthesis_prompt,
    build_workbench_synth_fn,
    gemini_probe_infer_fn,
    synthesize_workbench_briefing,
)


def test_build_synthesis_prompt_includes_goal_and_manifest() -> None:
    prompt = build_synthesis_prompt('{"summary": {}}', "arreglar el hook")
    assert "arreglar el hook" in prompt
    assert '"summary"' in prompt


def test_synthesize_returns_stripped_text_on_success() -> None:
    result = synthesize_workbench_briefing(
        "{}", "meta", infer_fn=lambda p: "  briefing real  "
    )
    assert result == "briefing real"


def test_synthesize_returns_none_when_infer_fn_raises() -> None:
    def _boom(p: str) -> str | None:
        raise RuntimeError("rate limited")

    assert synthesize_workbench_briefing("{}", "meta", infer_fn=_boom) is None


def test_synthesize_returns_none_when_infer_fn_returns_empty() -> None:
    assert synthesize_workbench_briefing("{}", "meta", infer_fn=lambda p: "") is None
    assert synthesize_workbench_briefing("{}", "meta", infer_fn=lambda p: None) is None


def test_synthesize_returns_none_when_manifest_is_blank() -> None:
    assert synthesize_workbench_briefing("   ", "meta", infer_fn=lambda p: "x") is None


class _FakeResponse:
    def __init__(self, *, success: bool, text: str = "") -> None:
        self.success = success
        self.text = text


class _FakeHub:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[str] = []

    def probe_provider(self, provider: Any, request: Any) -> _FakeResponse:
        self.calls.append(provider.name)
        return self._response


def test_gemini_probe_infer_fn_uses_gemini_free_without_fallback_chain() -> None:
    hub = _FakeHub(_FakeResponse(success=True, text="ok"))
    infer_fn = gemini_probe_infer_fn(hub)
    assert infer_fn("hola") == "ok"
    assert hub.calls == ["gemini_free"]


def test_gemini_probe_infer_fn_returns_none_on_failure() -> None:
    hub = _FakeHub(_FakeResponse(success=False))
    infer_fn = gemini_probe_infer_fn(hub)
    assert infer_fn("hola") is None


def test_build_workbench_synth_fn_composes_manifest_and_gemini() -> None:
    hub = _FakeHub(_FakeResponse(success=True, text="briefing"))
    synth = build_workbench_synth_fn(hub, lambda: '{"summary": {}}')
    assert synth("meta objetivo") == "briefing"


def test_build_workbench_synth_fn_fails_soft_when_manifest_fn_raises() -> None:
    class _NeverCalledHub:
        def probe_provider(self, provider: Any, request: Any) -> _FakeResponse:
            raise AssertionError("no debería llamarse si el manifiesto falla")

    def _boom() -> str:
        raise RuntimeError("sin backlog.yaml")

    synth = build_workbench_synth_fn(_NeverCalledHub(), _boom)
    assert synth("meta") is None
