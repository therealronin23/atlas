"""
Tests de cableado WriteGate (f2-4) → MCP de memoria (f2-11).

Verifica que:
- `MemoryTrunk.add` genera procedencia y pasa el ProvenanceWriteGate.
- Las escrituras crudas sin procedencia son rechazadas por el gate.
- El merkle_leaf_hash queda grabado (no None) tras un `add` legítimo.
- `MemoryTrunkRouter` con gate: el trunk por tenant aporta procedencia.
- `build_gated_index(require_provenance=True)` construye un índice con ProvenanceWriteGate.
- Sin gate, `MemoryTrunk.add` sigue funcionando igual que siempre.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import ProvenanceWriteGate, SqliteMemoryIndex, WriteRejected
from atlas.memory.record import GenericRecord
from atlas.mcp.memory_trunk import MemoryTrunk, MemoryTrunkRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gated_index(db: Path) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64), write_gate=ProvenanceWriteGate())


# ---------------------------------------------------------------------------
# a) add legítima pasa el gate y queda indexada
# ---------------------------------------------------------------------------


def test_add_passes_provenance_gate_and_is_recallable(tmp_path: Path) -> None:
    """trunk.add() aporta procedencia → ProvenanceWriteGate no rechaza."""
    index = _gated_index(tmp_path / "a.db")
    trunk = MemoryTrunk(index)
    # No debe lanzar WriteRejected
    rid = trunk.add("hecho legitimo")
    hits = trunk.recall("hecho")
    assert hits, "el record debe estar indexado tras add con gate"
    assert hits[0].record_id == rid


# ---------------------------------------------------------------------------
# b) escritura cruda sin procedencia es rechazada
# ---------------------------------------------------------------------------


def test_raw_upsert_without_provenance_is_rejected(tmp_path: Path) -> None:
    """index.upsert sin merkle_leaf_hash lanza WriteRejected bajo ProvenanceWriteGate."""
    index = _gated_index(tmp_path / "b.db")
    with pytest.raises(WriteRejected):
        index.upsert(GenericRecord("x", "texto", "0"))


# ---------------------------------------------------------------------------
# c) provenance presente tras add
# ---------------------------------------------------------------------------


def test_add_stores_non_none_merkle_leaf_hash(tmp_path: Path) -> None:
    """Tras trunk.add(...) el merkle_leaf_hash del record NO es None."""
    index = _gated_index(tmp_path / "c.db")
    trunk = MemoryTrunk(index)
    rid = trunk.add("dato con procedencia")
    mlh = index.merkle_leaf_hash(rid)
    assert mlh is not None, "merkle_leaf_hash debe quedar grabado"
    # debe ser un sha256 hexadecimal (64 chars)
    assert len(mlh) == 64


# ---------------------------------------------------------------------------
# d) router con gate por defecto y aislamiento por tenant
# ---------------------------------------------------------------------------


def test_router_with_gate_add_enters_and_tenant_isolation(tmp_path: Path) -> None:
    """MemoryTrunkRouter con ProvenanceWriteGate: add entra y el aislamiento se mantiene."""
    router = MemoryTrunkRouter(
        tmp_path / "d.db",
        embedder=StubEmbedder(dim=64),
        write_gate=ProvenanceWriteGate(),
    )
    trunk_a = router.for_tenant("a")
    trunk_b = router.for_tenant("b")

    # add de tenant A no lanza
    trunk_a.add("memoria exclusiva de A")

    # el trunk de A encuentra el record
    hits_a = trunk_a.recall("exclusiva A")
    assert hits_a, "tenant A debe ver su propio record"

    # el trunk de B no lo ve (aislamiento)
    hits_b = trunk_b.recall("exclusiva A")
    ids_b = [h.record_id for h in hits_b]
    ids_a = [h.record_id for h in hits_a]
    assert not any(rid in ids_b for rid in ids_a), "tenant B no debe ver records de tenant A"


# ---------------------------------------------------------------------------
# e) serve(require_provenance=True) → índice con ProvenanceWriteGate
# ---------------------------------------------------------------------------


def test_build_gated_index_require_provenance_rejects_raw_upsert(tmp_path: Path) -> None:
    """build_gated_index(require_provenance=True) produce un índice con ProvenanceWriteGate."""
    from atlas.mcp.memory_server import build_gated_index

    index = build_gated_index(tmp_path / "e.db", require_provenance=True)
    try:
        with pytest.raises(WriteRejected):
            index.upsert(GenericRecord("raw", "sin provenance", "0"))
        # Pero a través de MemoryTrunk.add sí entra
        trunk = MemoryTrunk(index)
        rid = trunk.add("con provenance")
        assert index.merkle_leaf_hash(rid) is not None
    finally:
        index.close()


def test_build_gated_index_default_no_gate_allows_raw_upsert(tmp_path: Path) -> None:
    """build_gated_index(require_provenance=False) (default) no bloquea escrituras crudas."""
    from atlas.mcp.memory_server import build_gated_index

    index = build_gated_index(tmp_path / "e2.db", require_provenance=False)
    try:
        # No debe lanzar
        index.upsert(GenericRecord("raw", "sin provenance", "0"))
    finally:
        index.close()


# ---------------------------------------------------------------------------
# f) sin gate, MemoryTrunk.add sigue funcionando
# ---------------------------------------------------------------------------


def test_add_without_gate_works_as_before(tmp_path: Path) -> None:
    """MemoryTrunk sobre índice sin write_gate: add funciona igual que siempre."""
    index = SqliteMemoryIndex(tmp_path / "f.db", embedder=StubEmbedder(dim=64))
    trunk = MemoryTrunk(index)
    rid = trunk.add("sin gate funciona igual")
    hits = trunk.recall("gate funciona")
    assert hits and hits[0].record_id == rid


def test_build_gated_index_uses_measured_semantic_threshold(tmp_path: Path) -> None:
    """La ruta semántica de producción usa el umbral MEDIDO 0.5, no el default
    0.8 del índice (que marcaba matched=False en el 100% de aciertos reales —
    medición 2026-07-17, ver comentario de _SEMANTIC_MATCH_THRESHOLD)."""
    from atlas.mcp.memory_server import _SEMANTIC_MATCH_THRESHOLD, build_gated_index

    index = build_gated_index(tmp_path / "thr.db")
    try:
        assert _SEMANTIC_MATCH_THRESHOLD == 0.5
        assert index._threshold == _SEMANTIC_MATCH_THRESHOLD
    finally:
        index.close()
