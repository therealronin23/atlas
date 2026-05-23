"""
Tests del MemoryDistiller (ADR-018, Gate D).
Verifica:
  - estimate_tokens es razonable
  - system chunks NUNCA se descartan
  - recent chunks se preservan
  - ranking por similarity respeta el budget
  - integracion con KuzuVectorStore via gather_relevant + build_context
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.distiller import (
    Chunk,
    ChunkSource,
    DistillationResult,
    MemoryDistiller,
    estimate_tokens,
)
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.vector_store import KuzuVectorStore


# ===========================================================================
# Helpers
# ===========================================================================


@pytest.fixture
def embedder() -> StubEmbedder:
    return StubEmbedder(dim=64)


@pytest.fixture
def distiller(embedder: StubEmbedder) -> MemoryDistiller:
    return MemoryDistiller(embedder=embedder, target_tokens=200)


@pytest.fixture
def vector_store(tmp_path: Path, embedder: StubEmbedder) -> KuzuVectorStore:
    return KuzuVectorStore(db_path=tmp_path / "distiller.kuzu", embedder=embedder)


# ===========================================================================
# estimate_tokens
# ===========================================================================


class TestEstimateTokens:

    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_monotonic(self) -> None:
        assert estimate_tokens("a") < estimate_tokens("a" * 100)

    def test_rough_4_chars_per_token(self) -> None:
        # 100 chars deberian ser ~25 tokens (cota superior)
        t = estimate_tokens("x" * 100)
        assert 20 <= t <= 30


# ===========================================================================
# distill — preservacion de system/recent y respeto del budget
# ===========================================================================


class TestDistillCore:

    def test_invalid_budget(self, distiller: MemoryDistiller) -> None:
        with pytest.raises(ValueError):
            distiller.distill("q", [], target_tokens=0)

    def test_invalid_target_tokens_at_init(self, embedder: StubEmbedder) -> None:
        with pytest.raises(ValueError):
            MemoryDistiller(embedder=embedder, target_tokens=0)

    def test_empty_chunks_ok(self, distiller: MemoryDistiller) -> None:
        result = distiller.distill("query", [])
        assert isinstance(result, DistillationResult)
        assert result.chunks == ()
        assert result.total_tokens == 0
        assert result.discarded_count == 0

    def test_system_chunks_always_included(
        self, distiller: MemoryDistiller
    ) -> None:
        system_text = "constitucion atlas " * 100  # ~2000 chars => ~500 tokens
        system = Chunk(text=system_text, source=ChunkSource.SYSTEM)
        result = distiller.distill("query", [system], target_tokens=50)
        # Aunque el budget sea muy chico, el system entra
        assert any(c.text == system_text for c in result.chunks)

    def test_recent_chunks_preserved_at_end(
        self, distiller: MemoryDistiller
    ) -> None:
        sys_c = Chunk(text="sys text", source=ChunkSource.SYSTEM)
        pat_c = Chunk(text="pattern about pytest filtering", source=ChunkSource.PATTERN)
        rec_c = Chunk(text="recent interaction snippet", source=ChunkSource.RECENT)
        result = distiller.distill("pytest filtering", [pat_c, sys_c, rec_c])
        # Orden: system primero, recent al final
        assert result.chunks[0].text == sys_c.text
        assert result.chunks[0].source == ChunkSource.SYSTEM
        assert result.chunks[-1].text == rec_c.text
        assert result.chunks[-1].source == ChunkSource.RECENT

    def test_relevance_ranks_scorable_chunks(
        self, distiller: MemoryDistiller
    ) -> None:
        relevant = Chunk(
            text="pytest -k filtra tests por nombre",
            source=ChunkSource.PATTERN,
        )
        unrelated = Chunk(
            text="tailscale despliega tunneles wireguard en servidores",
            source=ChunkSource.NOTE,
        )
        result = distiller.distill(
            "pytest filtrar tests",
            [unrelated, relevant],
            target_tokens=50,
        )
        # El relevante debe entrar antes que el irrelevante con budget chico
        chunk_texts = [c.text for c in result.chunks]
        assert relevant.text in chunk_texts

    def test_discards_when_over_budget(self, distiller: MemoryDistiller) -> None:
        chunks = [
            Chunk(text="x" * 200, source=ChunkSource.NOTE)
            for _ in range(10)
        ]
        result = distiller.distill("query", chunks, target_tokens=80)
        assert result.discarded_count > 0
        assert result.total_tokens <= 80

    def test_token_count_in_result(self, distiller: MemoryDistiller) -> None:
        chunks = [Chunk(text="hola mundo", source=ChunkSource.NOTE)]
        result = distiller.distill("query", chunks)
        assert result.total_tokens > 0
        assert result.budget == distiller.target_tokens
        assert result.strategy == "embed-rank-v1"

    def test_explicit_tokens_in_chunk_respected(
        self, distiller: MemoryDistiller
    ) -> None:
        # Si el chunk ya tiene tokens declarados, no se re-estima
        c = Chunk(text="x" * 1000, source=ChunkSource.NOTE, tokens=5)
        result = distiller.distill("q", [c])
        assert result.total_tokens == 5


# ===========================================================================
# gather_relevant + build_context
# ===========================================================================


class TestGatherRelevant:

    def test_no_vector_store_returns_empty(
        self, distiller: MemoryDistiller
    ) -> None:
        assert distiller.gather_relevant("query") == []

    def test_with_vector_store_returns_chunks(
        self, embedder: StubEmbedder, vector_store: KuzuVectorStore
    ) -> None:
        vector_store.add_pattern(
            "usar pytest -k para filtrar tests por nombre",
            tags=["pytest"],
            pattern_id="p1",
        )
        vector_store.add_pattern(
            "configurar tailscale en hetzner via auth key",
            tags=["tailscale"],
            pattern_id="p2",
        )
        vector_store.add_failure(
            error_type="ConnectionError",
            description="hermes 401 invalid key tras revocar",
            solution="regenerar groq api key",
        )

        d = MemoryDistiller(embedder, vector_store=vector_store)
        chunks = d.gather_relevant("pytest filtrar tests", max_patterns=3, max_failures=1)
        assert len(chunks) >= 1
        sources = {c.source for c in chunks}
        # Al menos un pattern y un failure deben estar
        assert ChunkSource.PATTERN in sources
        assert ChunkSource.FAILURE in sources

    def test_gather_respects_max_zero(
        self, embedder: StubEmbedder, vector_store: KuzuVectorStore
    ) -> None:
        vector_store.add_pattern("p1", pattern_id="p1")
        d = MemoryDistiller(embedder, vector_store=vector_store)
        # max_patterns=0 -> no extrae patterns aunque haya
        chunks = d.gather_relevant("q", max_patterns=0, max_failures=0, max_evidence=0)
        assert chunks == []


class TestBuildContext:

    def test_build_context_assembles_all_sources(
        self, embedder: StubEmbedder, vector_store: KuzuVectorStore
    ) -> None:
        vector_store.add_pattern(
            "pytest -k filtrado de tests",
            tags=["pytest"],
            pattern_id="p1",
        )
        d = MemoryDistiller(embedder, vector_store=vector_store, target_tokens=2000)
        text, result = d.build_context(
            query="pytest filtrar",
            system_chunks=["AXIOMA: Atlas es soberano local."],
            recent_chunks=["usuario: como filtro tests?"],
        )
        assert "AXIOMA" in text   # system preservado
        assert "usuario" in text  # recent preservado
        assert len(result.chunks) >= 2

    def test_build_context_without_vector_store(
        self, embedder: StubEmbedder
    ) -> None:
        d = MemoryDistiller(embedder, target_tokens=500)
        text, result = d.build_context(
            query="q",
            system_chunks=["sys content"],
            recent_chunks=["rec content"],
        )
        # Sin vector_store solo van system + recent
        assert text.startswith("sys content")
        assert text.endswith("rec content")
        assert len(result.chunks) == 2
