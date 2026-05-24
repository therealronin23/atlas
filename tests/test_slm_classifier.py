"""
Tests del SLMClassifier (ADR-010, Gate D/D2).
Verifica modo stub determinista, modo live mockeado, parseo del JSON,
fallbacks ante respuestas malformadas y cache via GhostReplay.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.core.contracts import RoutingLevel
from atlas.core.ghost_replay import GhostReplay
from atlas.core.inference_hub import (
    InferenceHub,
    InferenceLevel,
    InferenceResponse,
)
from atlas.router.slm_classifier import (
    SLMClassification,
    SLMClassifier,
    _parse_classification_json,
)


# ===========================================================================
# Stub mode (default en pytest)
# ===========================================================================


class TestStubMode:

    def test_governance_blocked(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("rm -rf /var/log")
        assert r.level == RoutingLevel.BLOCKED
        assert r.mode == "stub"

    def test_approval_required(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("borra el archivo viejo de logs")
        assert r.level == RoutingLevel.REQUIRES_APPROVAL

    def test_hermes_delegation(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("scrape la web cada hora cuando yo no este")
        assert r.level == RoutingLevel.DELEGATE_HERMES

    def test_deterministic_tool(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("lee el archivo notas.md")
        assert r.level == RoutingLevel.DETERMINISTIC_TOOL

    def test_local_safe_default(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("explicame que es un Merkle tree")
        assert r.level == RoutingLevel.LOCAL_SAFE

    def test_empty_intent(self) -> None:
        c = SLMClassifier(mode="stub")
        r = c.classify("")
        assert r.level == RoutingLevel.DETERMINISTIC_TOOL
        assert r.confidence == 0.0


# ===========================================================================
# Live mode (mocked InferenceHub)
# ===========================================================================


def _mock_hub_response(text: str, success: bool = True) -> MagicMock:
    hub = MagicMock(spec=InferenceHub)
    hub.infer.return_value = InferenceResponse(
        text=text,
        provider="mock",
        model="mock-model",
        level=InferenceLevel.L1,
        latency_ms=10,
        success=success,
        tokens_used=10,
        mode="live",
    )
    return hub


class TestLiveMode:

    def test_live_parses_valid_json(self) -> None:
        hub = _mock_hub_response(
            '{"level": "requires_approval", "confidence": 0.92, "reason": "git push detectado"}'
        )
        c = SLMClassifier(hub=hub, mode="live")
        r = c.classify("haz git push origin main")
        assert r.level == RoutingLevel.REQUIRES_APPROVAL
        assert r.confidence == pytest.approx(0.92)
        assert r.mode == "live"
        assert r.provider == "mock"

    def test_live_extracts_json_from_markdown_fence(self) -> None:
        wrapped = (
            "Claro, aqui esta:\n```json\n"
            '{"level": "local_safe", "confidence": 0.75, "reason": "consulta sencilla"}'
            "\n```\nFin."
        )
        hub = _mock_hub_response(wrapped)
        c = SLMClassifier(hub=hub, mode="live")
        r = c.classify("explicame Merkle")
        assert r.level == RoutingLevel.LOCAL_SAFE

    def test_live_invalid_json_falls_back(self) -> None:
        hub = _mock_hub_response("no es JSON, es texto plano")
        c = SLMClassifier(hub=hub, mode="live")
        r = c.classify("dame un consejo")
        assert r.level == RoutingLevel.LOCAL_SAFE
        assert "no parseable" in r.reason.lower() or "parsea" in r.reason.lower()

    def test_live_unknown_level_falls_back(self) -> None:
        hub = _mock_hub_response(
            '{"level": "wormhole", "confidence": 0.9, "reason": "x"}'
        )
        c = SLMClassifier(hub=hub, mode="live")
        r = c.classify("intent")
        assert r.level == RoutingLevel.LOCAL_SAFE
        assert "level desconocido" in r.reason.lower()

    def test_live_hub_failure_returns_fallback(self) -> None:
        hub = MagicMock(spec=InferenceHub)
        hub.infer.return_value = InferenceResponse(
            text="", provider="x", model="m",
            level=InferenceLevel.L1,
            latency_ms=0, success=False,
            error="rate limit", mode="live",
        )
        c = SLMClassifier(hub=hub, mode="live")
        r = c.classify("query")
        assert r.level == RoutingLevel.LOCAL_SAFE
        assert "fallback" in r.reason.lower()


# ===========================================================================
# Auto mode (deberia caer a stub en pytest)
# ===========================================================================


class TestAutoMode:

    def test_auto_falls_to_stub_in_pytest(self) -> None:
        # Aun con hub, si estamos en pytest -> stub
        hub = _mock_hub_response('{"level":"local_safe","confidence":0.5,"reason":"x"}')
        c = SLMClassifier(hub=hub, mode="auto")
        r = c.classify("intent")
        # El hub NO se debe llamar
        hub.infer.assert_not_called()
        assert r.mode == "stub"


# ===========================================================================
# Cache via GhostReplay
# ===========================================================================


class TestCacheIntegration:

    def test_cache_hit_short_circuits(self, tmp_path: Path) -> None:
        cache = GhostReplay(tmp_path / "ghost")
        # Pre-cargar una clasificacion
        cache.record(
            "intent X", "classification", "slm-classifier-v1",
            {
                "level":      "delegate_hermes",
                "confidence": 0.88,
                "reason":     "cacheado",
                "provider":   "cached-mock",
                "raw_text":   None,
            },
        )
        # Hub que pinchara si se invoca:
        hub = MagicMock(spec=InferenceHub)
        hub.infer.side_effect = AssertionError("no debe invocarse cuando hay cache hit")
        c = SLMClassifier(hub=hub, mode="live", ghost_replay=cache)
        r = c.classify("intent X")
        assert r.mode == "cache"
        assert r.level == RoutingLevel.DELEGATE_HERMES
        assert r.confidence == pytest.approx(0.88)
        hub.infer.assert_not_called()

    def test_cache_store_after_live(self, tmp_path: Path) -> None:
        cache = GhostReplay(tmp_path / "ghost")
        hub = _mock_hub_response(
            '{"level":"local_safe","confidence":0.7,"reason":"OK"}'
        )
        c = SLMClassifier(hub=hub, mode="live", ghost_replay=cache)
        c.classify("intent Y")
        # Segundo lookup debe acertar
        hit = cache.lookup("intent Y", "classification", "slm-classifier-v1")
        assert hit is not None
        assert hit.result["level"] == "local_safe"


# ===========================================================================
# _parse_classification_json — extraccion robusta
# ===========================================================================


class TestJSONParser:

    def test_plain_json(self) -> None:
        out = _parse_classification_json(
            '{"level": "local_safe", "confidence": 0.8, "reason": "x"}'
        )
        assert out == ("local_safe", 0.8, "x")

    def test_markdown_fenced(self) -> None:
        text = '```json\n{"level":"blocked","confidence":1.0,"reason":"sudo"}\n```'
        out = _parse_classification_json(text)
        assert out is not None
        assert out[0] == "blocked"

    def test_embedded_in_prose(self) -> None:
        text = (
            "Aqui esta mi respuesta: "
            '{"level":"deterministic_tool","confidence":0.95,"reason":"git status"} '
            "espero que ayude."
        )
        out = _parse_classification_json(text)
        assert out is not None
        assert out[0] == "deterministic_tool"

    def test_clamps_confidence(self) -> None:
        text = '{"level":"local_safe","confidence":99,"reason":"oversized"}'
        out = _parse_classification_json(text)
        assert out is not None
        assert out[1] == 1.0

    def test_invalid_returns_none(self) -> None:
        assert _parse_classification_json("") is None
        assert _parse_classification_json("garbage") is None
        assert _parse_classification_json('{"foo": "bar"}') is None


# ===========================================================================
# Constructor edge cases
# ===========================================================================


class TestConstructor:

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValueError):
            SLMClassifier(mode="bogus")

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_SLM_CLASSIFIER_MODE", "stub")
        c = SLMClassifier(mode="live")
        assert c.mode == "stub"


# ===========================================================================
# MemoryDistiller integration (FU-5)
# ===========================================================================


class TestSLMClassifierWithDistiller:
    """FU-5 — SLMClassifier acepta MemoryDistiller y lo usa en _build_context."""

    def _mock_distiller(self, returns: str = "contexto comprimido por distiller") -> MagicMock:
        d = MagicMock()
        d.build_context.return_value = (returns, [])
        return d

    def test_build_context_without_distiller_returns_system_prompt(self) -> None:
        from atlas.router.slm_classifier import SLM_SYSTEM_PROMPT
        clf = SLMClassifier(mode="stub")
        ctx = clf._build_context("cualquier intent")
        assert ctx == SLM_SYSTEM_PROMPT

    def test_build_context_with_distiller_returns_distilled(self) -> None:
        d = self._mock_distiller("contexto distilado relevante")
        clf = SLMClassifier(mode="stub", distiller=d)
        ctx = clf._build_context("explícame el sistema de permisos de Atlas")
        assert ctx == "contexto distilado relevante"
        d.build_context.assert_called_once()

    def test_build_context_distiller_called_with_intent_as_query(self) -> None:
        d = self._mock_distiller()
        clf = SLMClassifier(mode="stub", distiller=d)
        clf._build_context("intent de prueba")
        call_kwargs = d.build_context.call_args
        assert call_kwargs.kwargs.get("query") == "intent de prueba"

    def test_build_context_distiller_exception_falls_back_to_system_prompt(self) -> None:
        from atlas.router.slm_classifier import SLM_SYSTEM_PROMPT
        d = MagicMock()
        d.build_context.side_effect = RuntimeError("distiller error")
        clf = SLMClassifier(mode="stub", distiller=d)
        ctx = clf._build_context("intent")
        assert ctx == SLM_SYSTEM_PROMPT  # fallback silencioso

    def test_live_classify_uses_distilled_context(self) -> None:
        """En modo live, el context del InferenceRequest viene de _build_context."""
        d = self._mock_distiller("contexto distilado para live")
        hub = MagicMock(spec=InferenceHub)
        hub.infer.return_value = InferenceResponse(
            success=True,
            text='{"level":"local_safe","confidence":0.8,"reason":"test"}',
            provider="groq", model="llama-3.3", latency_ms=100,
            level=InferenceLevel.L1,
        )
        clf = SLMClassifier(hub=hub, mode="live", distiller=d)
        clf.classify("test intent live")
        req = hub.infer.call_args[0][0]
        assert req.context == "contexto distilado para live"
