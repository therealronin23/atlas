"""
Tests de KuzuVectorStore (Gate D/D4).
Usa StubEmbedder + tmp_path DB para aislamiento total.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.vector_store import (
    KuzuVectorStore,
    PatternHit,
    VectorStoreError,
    cosine_similarity,
)


@pytest.fixture
def store(tmp_path: Path) -> KuzuVectorStore:
    return KuzuVectorStore(
        db_path=tmp_path / "kuzu.db",
        embedder=StubEmbedder(dim=64),
    )


class TestSchemaLifecycle:

    def test_open_creates_schema_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "lifecycle.db"
        s1 = KuzuVectorStore(db_path=path, embedder=StubEmbedder(dim=32))
        s1.close()
        # Reabrir con el mismo embedder no debe fallar
        s2 = KuzuVectorStore(db_path=path, embedder=StubEmbedder(dim=32))
        assert s2.dim == 32

    def test_dim_mismatch_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "mismatch.db"
        s1 = KuzuVectorStore(db_path=path, embedder=StubEmbedder(dim=32))
        s1.close()
        with pytest.raises(VectorStoreError, match="Dim mismatch"):
            KuzuVectorStore(db_path=path, embedder=StubEmbedder(dim=64))

    def test_recreate_wipes_db(self, tmp_path: Path) -> None:
        path = tmp_path / "recreate.db"
        s1 = KuzuVectorStore(db_path=path, embedder=StubEmbedder(dim=32))
        s1.add_pattern("uno")
        s1.close()

        s2 = KuzuVectorStore(
            db_path=path, embedder=StubEmbedder(dim=64), recreate=True
        )
        assert s2.count("Pattern") == 0


class TestPatternInsertSearch:

    def test_add_returns_id(self, store: KuzuVectorStore) -> None:
        pid = store.add_pattern("usar pytest -k para filtrar tests")
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_add_with_explicit_id(self, store: KuzuVectorStore) -> None:
        pid = store.add_pattern("foo", pattern_id="p-001")
        assert pid == "p-001"

    def test_get_pattern(self, store: KuzuVectorStore) -> None:
        pid = store.add_pattern("descripcion del patron", tags=["a", "b"])
        got = store.get_pattern(pid)
        assert got is not None
        assert got["text"] == "descripcion del patron"
        assert got["tags"] == ["a", "b"]

    def test_count(self, store: KuzuVectorStore) -> None:
        assert store.count("Pattern") == 0
        store.add_pattern("uno")
        store.add_pattern("dos")
        store.add_pattern("tres")
        assert store.count("Pattern") == 3

    def test_search_returns_best_match(self, store: KuzuVectorStore) -> None:
        store.add_pattern("pytest -k filtra tests por nombre", pattern_id="A")
        store.add_pattern("desplegar tailscale en el VPS", pattern_id="B")
        store.add_pattern("escribir un Dockerfile multistage", pattern_id="C")

        hits = store.find_similar_patterns("pytest filtrar tests", top_k=3)
        assert len(hits) == 3
        assert isinstance(hits[0], PatternHit)
        # El primero debe ser A (palabras compartidas: pytest, filtrar, tests)
        assert hits[0].id == "A"
        assert hits[0].score > hits[1].score

    def test_search_top_k_respected(self, store: KuzuVectorStore) -> None:
        for i in range(10):
            store.add_pattern(f"patron numero {i}")
        hits = store.find_similar_patterns("patron", top_k=3)
        assert len(hits) == 3


class TestFailureAndEvidence:

    def test_add_and_search_failure(self, store: KuzuVectorStore) -> None:
        fid = store.add_failure(
            error_type="ConnectionError",
            description="hermes no responde tras 3 reintentos",
            solution="activar OfflineQueue y avisar via Telegram",
        )
        assert fid
        hits = store.find_similar_failures("hermes timeout reintentos")
        assert len(hits) == 1
        assert hits[0].id == fid

    def test_add_and_search_evidence(self, store: KuzuVectorStore) -> None:
        eid = store.add_evidence(
            "groq devuelve 401 si la key fue revocada",
            source="smoke_test_2026_05_23",
        )
        assert eid
        hits = store.find_similar_evidence("groq 401 invalid key")
        assert hits[0].id == eid


class TestGraphEdges:

    def test_link_derived_from(self, store: KuzuVectorStore) -> None:
        fid = store.add_failure(
            error_type="X", description="d", solution="s",
        )
        pid = store.add_pattern("patron derivado del fallo")
        store.link_derived_from(pid, fid)
        # No exception = OK; revisamos via Cypher directo
        result = store._conn.execute(
            "MATCH (p:Pattern)-[:DERIVED_FROM]->(f:Failure) RETURN p.id, f.id"
        )
        rows = list(result)
        assert any(row[0] == pid and row[1] == fid for row in rows)

    def test_link_similar(self, store: KuzuVectorStore) -> None:
        a = store.add_pattern("patron A")
        b = store.add_pattern("patron B")
        store.link_similar(a, b, similarity=0.83)
        result = store._conn.execute(
            "MATCH (a:Pattern)-[r:SIMILAR_TO]->(b:Pattern) RETURN a.id, b.id, r.similarity"
        )
        rows = list(result)
        assert (a, b, 0.83) in [(r[0], r[1], r[2]) for r in rows]


class TestCosineSimilarity:

    def test_orthogonal_vectors_zero(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_identical_vectors_one(self) -> None:
        a = [0.5, 0.5, 0.5, 0.5]
        assert cosine_similarity(a, a) == pytest.approx(1.0)

    def test_opposite_vectors_minus_one(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_dim_mismatch_returns_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0, 0.0], [1.0, 1.0, 1.0]) == 0.0


class TestInvalidNodeType:

    def test_count_rejects_unknown(self, store: KuzuVectorStore) -> None:
        with pytest.raises(VectorStoreError):
            store.count("Bogus")
