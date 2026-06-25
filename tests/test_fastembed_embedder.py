"""Tests del embedder local fastembed + el selector `default_embedder`."""

from __future__ import annotations

import importlib.util

import pytest

from atlas.memory.embeddings import StubEmbedder, default_embedder

_HAS_FASTEMBED = importlib.util.find_spec("fastembed") is not None


def test_default_embedder_is_stub_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_EMBEDDER", raising=False)
    emb = default_embedder()
    assert isinstance(emb, StubEmbedder)
    assert emb.dim == 64


def test_default_embedder_stub_on_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_EMBEDDER", "nope")
    assert isinstance(default_embedder(), StubEmbedder)


def test_fastembed_fail_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    if _HAS_FASTEMBED:
        pytest.skip("fastembed instalado: no se puede probar el camino fail-closed")
    monkeypatch.setenv("ATLAS_EMBEDDER", "fastembed")
    # Fail-closed: NO cae a stub callado — propaga un RuntimeError explícito.
    with pytest.raises(RuntimeError, match="fastembed no instalado"):
        default_embedder()


@pytest.mark.skipif(not _HAS_FASTEMBED, reason="requiere el extra [embeddings]")
def test_fastembed_selected_and_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas.memory.embeddings import FastEmbedEmbedder

    monkeypatch.setenv("ATLAS_EMBEDDER", "fastembed")
    emb = default_embedder()
    assert isinstance(emb, FastEmbedEmbedder)
    assert emb.dim == 384


@pytest.mark.skipif(not _HAS_FASTEMBED, reason="requiere el extra [embeddings]")
def test_fastembed_is_semantic_spanish() -> None:
    """verify-the-real-case: vectores reales donde frases relacionadas (en español)
    quedan más cerca que frases no relacionadas — lo que el stub NO logra."""
    import math

    from atlas.memory.embeddings import FastEmbedEmbedder

    emb = FastEmbedEmbedder()
    v_perro, v_can, v_banco = emb.embed_batch(
        ["el perro corre por el parque", "un can juega en el jardín", "tipos de interés del banco central"]
    )
    assert len(v_perro) == 384

    def cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    # perro~can (mismo tema) debe superar a perro~banco (temas distintos).
    assert cos(v_perro, v_can) > cos(v_perro, v_banco)
