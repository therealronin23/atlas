"""Tests del embedder local fastembed + el selector `default_embedder`."""

from __future__ import annotations

import importlib.util

import pytest

from atlas.memory.embeddings import FastEmbedEmbedder, StubEmbedder, default_embedder

_HAS_FASTEMBED = importlib.util.find_spec("fastembed") is not None


@pytest.mark.skipif(not _HAS_FASTEMBED, reason="requiere el extra [embeddings]")
def test_default_embedder_is_fastembed_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-07-03: el default cambió de stub->fastembed (store real sin datos
    que migrar, verificado antes del cambio)."""
    monkeypatch.delenv("ATLAS_EMBEDDER", raising=False)
    emb = default_embedder()
    assert isinstance(emb, FastEmbedEmbedder)
    assert emb.dim == 384


def test_default_embedder_stub_on_explicit_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """ATLAS_EMBEDDER=stub sigue siendo el opt-out explícito (tests/CI que no
    quieran cargar el modelo ONNX)."""
    monkeypatch.setenv("ATLAS_EMBEDDER", "stub")
    assert isinstance(default_embedder(), StubEmbedder)


@pytest.mark.skipif(not _HAS_FASTEMBED, reason="requiere el extra [embeddings]")
def test_default_embedder_unknown_value_falls_back_to_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier valor que no sea literalmente 'stub' cae al default actual
    (fastembed) — solo 'stub' es el opt-out reconocido."""
    monkeypatch.setenv("ATLAS_EMBEDDER", "nope")
    assert isinstance(default_embedder(), FastEmbedEmbedder)


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
