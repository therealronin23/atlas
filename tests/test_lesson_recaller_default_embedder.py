"""
LessonRecaller usa default_embedder() (gobernado por ATLAS_EMBEDDER) en vez de
StubEmbedder hardcodeado — respuesta al hueco detectado en vivo: threshold=0.8
(razonable para embeddings SEMÁNTICOS) era demasiado estricto para el hash de
StubEmbedder, dejando la memoria de lecciones prácticamente inconsultable con
el default de entonces (stub). 2026-07-03: el default de `default_embedder()`
cambió a fastembed (semántico) precisamente para cerrar este hueco — ahora el
comportamiento SIN configurar nada ya es el semántico, coherente con el
threshold=0.8. `ATLAS_EMBEDDER=stub` sigue siendo el opt-out explícito.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.verify import Verdict
from atlas.immunity.lesson_recaller import LessonRecaller
from atlas.memory.embeddings import StubEmbedder


def _lesson(lid: str, pattern: str) -> Lesson:
    return Lesson(
        id=lid, title=lid, detection_heuristic="h", avoid_pattern=pattern,
        provenance=LessonProvenance.INTERNAL_FAILURE,
        evidence={"verdict": Verdict.PASS.value},
    )


def test_default_embedder_without_env_var_is_fastembed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin ATLAS_EMBEDDER, el default ahora es el semántico (fastembed,
    2026-07-03) — cierra el hueco real de threshold=0.8 vs stub."""
    monkeypatch.delenv("ATLAS_EMBEDDER", raising=False)
    store = LessonStore(tmp_path / "lessons")
    recaller = LessonRecaller(store)
    from atlas.memory.embeddings import FastEmbedEmbedder
    assert isinstance(recaller._embedder, FastEmbedEmbedder)


def test_atlas_embedder_env_var_stub_opts_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Con ATLAS_EMBEDDER=stub, LessonRecaller sigue pudiendo usar el hash
    barato explícitamente (opt-out, p.ej. para tests/CI)."""
    monkeypatch.setenv("ATLAS_EMBEDDER", "stub")
    store = LessonStore(tmp_path / "lessons")
    recaller = LessonRecaller(store)
    assert isinstance(recaller._embedder, StubEmbedder)


def test_fastembed_default_finds_paraphrase_stub_misses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verificación real (no solo 'los tests pasan') de que el cambio de default
    mejora el recall semántico: una lección y una consulta que dicen lo MISMO
    con palabras DISTINTAS (parafraseo, sin solapamiento léxico) — el hash de
    StubEmbedder no puede verlo, fastembed sí."""
    monkeypatch.delenv("ATLAS_EMBEDDER", raising=False)  # default real: fastembed
    store = LessonStore(tmp_path / "lessons")
    store.add(_lesson(
        "sql-concat",
        "Nunca concatenar texto del usuario directamente dentro de una consulta SQL",
    ))
    recaller = LessonRecaller(store)
    recaller.index()

    # Mismo concepto, sin ninguna palabra literal compartida con avoid_pattern.
    result = recaller.recall("unir cadenas sin sanear en una sentencia de base de datos")
    assert result is not None
    assert result.lesson_id == "sql-concat"
    fastembed_score = result.score

    # El mismo escenario con el hash de StubEmbedder (opt-out explícito): al no
    # compartir tokens, el score debe quedar bajo — demuestra la mejora real.
    monkeypatch.setenv("ATLAS_EMBEDDER", "stub")
    store_stub = LessonStore(tmp_path / "lessons_stub")
    store_stub.add(_lesson(
        "sql-concat",
        "Nunca concatenar texto del usuario directamente dentro de una consulta SQL",
    ))
    recaller_stub = LessonRecaller(store_stub)
    recaller_stub.index()
    result_stub = recaller_stub.recall("unir cadenas sin sanear en una sentencia de base de datos")
    stub_score = result_stub.score if result_stub is not None else 0.0

    assert fastembed_score > stub_score


def test_explicit_embedder_still_overrides_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pasar embedder= explícito sigue ganando sobre la variable de entorno."""
    monkeypatch.setenv("ATLAS_EMBEDDER", "fastembed")
    store = LessonStore(tmp_path / "lessons")
    explicit = StubEmbedder(dim=32)
    recaller = LessonRecaller(store, embedder=explicit)
    assert recaller._embedder is explicit
