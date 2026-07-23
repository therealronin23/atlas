"""
Tests del modulo de embeddings (Gate D/D4).
StubEmbedder deterministico + LiteLLMEmbedder mockeado.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock

import pytest

import litellm

from atlas.memory.embeddings import (
    LiteLLMEmbedder,
    LiteLLMEmbedderConfig,
    PRESET_OPENAI_SMALL,
    StubEmbedder,
)


class TestStubEmbedder:

    def test_dim_property(self) -> None:
        e = StubEmbedder(dim=32)
        assert e.dim == 32

    def test_deterministic_same_input(self) -> None:
        e = StubEmbedder(dim=64)
        v1 = e.embed("hola mundo")
        v2 = e.embed("hola mundo")
        assert v1 == v2

    def test_normalized_l2(self) -> None:
        e = StubEmbedder(dim=64)
        v = e.embed("atlas core inference hub")
        norm = math.sqrt(sum(x * x for x in v))
        assert math.isclose(norm, 1.0, abs_tol=1e-9)

    def test_different_texts_different_vectors(self) -> None:
        e = StubEmbedder(dim=64)
        a = e.embed("usar pytest -k para filtrar tests")
        b = e.embed("desplegar tailscale en el VPS")
        assert a != b

    def test_overlap_increases_similarity(self) -> None:
        # Stub no es semantico, pero textos con palabras compartidas deberian
        # ser mas cercanos que textos completamente distintos.
        e = StubEmbedder(dim=128)
        from atlas.memory.vector_store import cosine_similarity

        a = e.embed("hola atlas atlas atlas")
        b = e.embed("hola atlas atlas")
        c = e.embed("xyz qwerty distinto")
        assert cosine_similarity(a, b) > cosine_similarity(a, c)

    def test_empty_string(self) -> None:
        e = StubEmbedder(dim=16)
        v = e.embed("")
        assert len(v) == 16

    def test_batch(self) -> None:
        e = StubEmbedder(dim=32)
        out = e.embed_batch(["uno", "dos", "tres"])
        assert len(out) == 3
        assert all(len(v) == 32 for v in out)


class TestLiteLLMEmbedderAutoMode:

    def test_auto_in_pytest_uses_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "fake")  # incluso con key, pytest activo -> stub
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="auto")

        def boom(**kwargs: Any) -> Any:  # pragma: no cover
            raise AssertionError("no deberia llamar litellm.embedding en pytest")

        monkeypatch.setattr(litellm, "embedding", boom)
        v = emb.embed("hola")
        assert len(v) == PRESET_OPENAI_SMALL.dim   # 1536

    def test_stub_mode_explicit(self) -> None:
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="stub")
        v = emb.embed("hola")
        assert len(v) == PRESET_OPENAI_SMALL.dim


class TestLiteLLMEmbedderLiveMode:

    def test_live_calls_litellm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        captured: dict[str, Any] = {}

        def fake_embedding(**kwargs: Any) -> Any:
            captured.update(kwargs)
            n = len(kwargs["input"])
            resp = MagicMock()
            resp.data = [{"embedding": [0.1] * 1536} for _ in range(n)]
            return resp

        monkeypatch.setattr(litellm, "embedding", fake_embedding)
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="live")
        v = emb.embed("test")
        assert len(v) == 1536
        assert captured["model"] == "openai/text-embedding-3-small"
        assert captured["api_key"] == "test-key"

    def test_batch_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")

        def fake_embedding(**kwargs: Any) -> Any:
            n = len(kwargs["input"])
            resp = MagicMock()
            resp.data = [{"embedding": [0.0] * 1536} for _ in range(n)]
            return resp

        monkeypatch.setattr(litellm, "embedding", fake_embedding)
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="live")
        vs = emb.embed_batch(["a", "b", "c"])
        assert len(vs) == 3

    def test_live_rejects_dim_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")

        def bad_dim_embedding(**kwargs: Any) -> Any:
            resp = MagicMock()
            resp.data = [{"embedding": [0.0] * 999}]  # dim incorrecta
            return resp

        monkeypatch.setattr(litellm, "embedding", bad_dim_embedding)
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="live")
        with pytest.raises(RuntimeError, match="dim inesperada"):
            emb.embed("x")


class TestLiteLLMEmbedderEdgeCases:

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError):
            LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="bogus")

    def test_stub_dim_mismatch_rejected(self) -> None:
        bad_stub = StubEmbedder(dim=99)
        with pytest.raises(ValueError):
            LiteLLMEmbedder(PRESET_OPENAI_SMALL, stub_fallback=bad_stub)

    def test_empty_batch(self) -> None:
        emb = LiteLLMEmbedder(PRESET_OPENAI_SMALL, mode="stub")
        assert emb.embed_batch([]) == []


class TestFastEmbedModelCache:
    """El modelo ONNX se carga UNA vez por proceso (2026-07-10): cada carga
    cuesta ~500MB de RSS que el allocator no devuelve al SO ni liberando la
    instancia — sin cache, la suite acumulaba 7.5GB y earlyoom la mataba."""

    def test_two_instances_share_one_model_load(self, tmp_path, monkeypatch) -> None:
        import sys
        import types

        loads: list[str] = []
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"fake-model")

        class _ConcreteModel:
            _model_dir = model_dir

        class _FakeModel:
            def __init__(self, model_name: str, **kwargs: object) -> None:
                loads.append(model_name)
                self.model = _ConcreteModel()

            def embed(self, texts):
                return [[0.0] * 384 for _ in texts]

        fake = types.ModuleType("fastembed")
        fake.TextEmbedding = lambda model_name, **kwargs: _FakeModel(model_name, **kwargs)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fake)

        from atlas.memory.embeddings import FastEmbedEmbedder

        monkeypatch.setattr(FastEmbedEmbedder, "_MODEL_CACHE", {})
        monkeypatch.setattr(FastEmbedEmbedder, "_ARTIFACT_DIGEST_CACHE", {})
        a = FastEmbedEmbedder(model_name="m-test", dim=384)
        b = FastEmbedEmbedder(model_name="m-test", dim=384)
        assert loads == ["m-test"]  # una sola carga
        assert a._model is b._model  # instancia compartida
        # Modelo distinto = carga propia (no se mezclan vectores de modelos).
        FastEmbedEmbedder(model_name="otro", dim=384)
        assert loads == ["m-test", "otro"]
