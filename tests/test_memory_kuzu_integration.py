"""
Tests de integracion memory_system <-> KuzuVectorStore (Gate D/D4).
ErrorRegistry y ApprovedPatternStore deben replicar a Kuzu cuando se
les inyecta el vector_store, sin romper la API existente cuando no.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_system import (
    ApprovedPatternStore,
    ErrorRegistry,
    FailureEntry,
    PatternEntry,
)
from atlas.memory.vector_store import KuzuVectorStore


@pytest.fixture
def vector_store(tmp_path: Path) -> KuzuVectorStore:
    return KuzuVectorStore(
        db_path=tmp_path / "memory.kuzu",
        embedder=StubEmbedder(dim=32),
    )


# ---------------------------------------------------------------------------
# Backward compat: sin vector_store, comportamiento intacto
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:

    def test_error_registry_no_vector_store(self, tmp_path: Path) -> None:
        reg = ErrorRegistry(tmp_path / "fails")
        entry = FailureEntry(
            id="f-1",
            error_type="TimeoutError",
            description="hermes no responde",
            context={},
            solution="reintentar",
        )
        reg.record(entry)
        assert reg.find_similar("hermes") == []   # sin vs no hay busqueda
        results = reg.search("TimeoutError")
        assert len(results) == 1

    def test_pattern_store_no_vector_store(self, tmp_path: Path) -> None:
        store = ApprovedPatternStore(tmp_path / "patterns")
        entry = PatternEntry(
            id="p-1", name="n", description="d", pattern_type="code", content="c",
        )
        store.add(entry)
        assert store.find_similar("n") == []


# ---------------------------------------------------------------------------
# Con vector_store: replicacion automatica + busqueda semantica
# ---------------------------------------------------------------------------


class TestErrorRegistryWithKuzu:

    def test_record_mirrors_to_kuzu(
        self, tmp_path: Path, vector_store: KuzuVectorStore
    ) -> None:
        reg = ErrorRegistry(tmp_path / "fails", vector_store=vector_store)
        reg.record(FailureEntry(
            id="f-1",
            error_type="ConnectionError",
            description="groq devuelve 401",
            context={},
            solution="regenerar la API key",
        ))
        assert vector_store.count("Failure") == 1

    def test_find_similar_returns_failures(
        self, tmp_path: Path, vector_store: KuzuVectorStore
    ) -> None:
        reg = ErrorRegistry(tmp_path / "fails", vector_store=vector_store)
        reg.record(FailureEntry(
            id="f-1",
            error_type="ConnectionError",
            description="groq devuelve 401 invalid key",
            context={},
            solution="regenerar API key",
        ))
        reg.record(FailureEntry(
            id="f-2",
            error_type="TimeoutError",
            description="VPS Hetzner no responde",
            context={},
            solution="rebootear contenedor",
        ))

        hits = reg.find_similar("groq 401 key")
        assert len(hits) > 0
        assert hits[0].id == "f-1"


class TestPatternStoreWithKuzu:

    def test_add_mirrors_to_kuzu(
        self, tmp_path: Path, vector_store: KuzuVectorStore
    ) -> None:
        store = ApprovedPatternStore(tmp_path / "patterns", vector_store=vector_store)
        store.add(PatternEntry(
            id="p-1",
            name="n",
            description="usar pytest -k para filtrar",
            pattern_type="code",
            content="pytest -k 'nombre'",
        ))
        assert vector_store.count("Pattern") == 1

    def test_find_similar_returns_patterns(
        self, tmp_path: Path, vector_store: KuzuVectorStore
    ) -> None:
        store = ApprovedPatternStore(tmp_path / "patterns", vector_store=vector_store)
        store.add(PatternEntry(
            id="p-1",
            name="pytest filtrado",
            description="usar pytest -k nombre para filtrar tests",
            pattern_type="code",
            content="pytest -k",
        ))
        store.add(PatternEntry(
            id="p-2",
            name="tailscale deploy",
            description="desplegar tailscale en VPS Hetzner",
            pattern_type="workflow",
            content="curl ... tailscale up",
        ))

        hits = store.find_similar("pytest filtrar tests")
        assert hits[0].id == "p-1"


# ---------------------------------------------------------------------------
# Robustez: vector_store puede fallar sin romper la verdad bruta (JSON)
# ---------------------------------------------------------------------------


class TestVectorFailureIsNonFatal:

    def test_record_persists_json_even_if_kuzu_fails(
        self, tmp_path: Path, vector_store: KuzuVectorStore
    ) -> None:
        reg = ErrorRegistry(tmp_path / "fails", vector_store=vector_store)
        # Insertar primero
        reg.record(FailureEntry(
            id="f-collision",
            error_type="X", description="x", context={}, solution="x",
        ))
        # Insertar otra con el MISMO id — Kuzu rechazara por PK duplicado.
        # El JSON debe seguir escribiendose (sobreescribe).
        reg.record(FailureEntry(
            id="f-collision",
            error_type="Y", description="y", context={}, solution="y",
        ))
        results = reg.search("Y")
        assert len(results) == 1
        assert results[0].description == "y"
