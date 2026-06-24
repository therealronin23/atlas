"""
Tests TDD para aislamiento por tenant (multi-tenancy) en SqliteMemoryIndex.

Criterios de aceptación:
  a) Aislamiento en recall: recall de A nunca devuelve ids de B (y viceversa).
     recall_all(k grande) de A solo devuelve ids de A.
  b) Aislamiento en recall_multihop: la cadena de A solo contiene ids de A.
  c) Aislamiento en text_of: idx_a.text_of("b-3") → None.
  d) Conteos por tenant: count y active_count correctos por tenant.
  e) rebuild_from no borra otros tenants.
  f) upsert guard: si A tiene id="x" y B hace upsert con record_id="x" → ValueError.
  g) Compat default: SqliteMemoryIndex(db) sin tenant funciona como antes.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


def _shared_db(tmp_path: Path) -> Path:
    return tmp_path / "shared.db"


def _make_pair(db: Path) -> tuple[SqliteMemoryIndex, SqliteMemoryIndex]:
    """Crea dos instancias sobre el mismo fichero, una por tenant."""
    emb = StubEmbedder(dim=64)
    idx_a = SqliteMemoryIndex(db, tenant="tenant-a", embedder=emb)
    idx_b = SqliteMemoryIndex(db, tenant="tenant-b", embedder=emb)
    return idx_a, idx_b


def _populate(
    idx_a: SqliteMemoryIndex,
    idx_b: SqliteMemoryIndex,
    n: int = 10,
) -> None:
    for i in range(n):
        idx_a.upsert(_rec(f"a-{i}", f"texto de tenant-a numero {i}"))
        idx_b.upsert(_rec(f"b-{i}", f"texto de tenant-b numero {i}"))


class TestTenantIsolation:
    # ------------------------------------------------------------------
    # a) Aislamiento en recall y recall_all
    # ------------------------------------------------------------------
    def test_recall_does_not_leak_across_tenants(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        # Query que matchea textos de B
        result_a = idx_a.recall("texto de tenant-b numero 3")
        if result_a is not None:
            assert result_a.lesson_id.startswith("a-"), (
                f"recall de A devolvió id de B: {result_a.lesson_id}"
            )

        result_b = idx_b.recall("texto de tenant-a numero 7")
        if result_b is not None:
            assert result_b.lesson_id.startswith("b-"), (
                f"recall de B devolvió id de A: {result_b.lesson_id}"
            )

    def test_recall_all_only_returns_own_ids(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        results_a = idx_a.recall_all("texto", k=100)
        for r in results_a:
            assert r.lesson_id.startswith("a-"), (
                f"recall_all de A incluyó id de B: {r.lesson_id}"
            )

        results_b = idx_b.recall_all("texto", k=100)
        for r in results_b:
            assert r.lesson_id.startswith("b-"), (
                f"recall_all de B incluyó id de A: {r.lesson_id}"
            )

    # ------------------------------------------------------------------
    # b) Aislamiento en recall_multihop
    # ------------------------------------------------------------------
    def test_recall_multihop_only_returns_own_ids(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        chain_a = idx_a.recall_multihop("texto de tenant-a numero 0", hops=5)
        for r in chain_a:
            assert r.lesson_id.startswith("a-"), (
                f"recall_multihop de A incluyó id de B: {r.lesson_id}"
            )

    # ------------------------------------------------------------------
    # c) Aislamiento en text_of
    # ------------------------------------------------------------------
    def test_text_of_cross_tenant_returns_none(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        # A no puede leer texto de ids de B
        assert idx_a.text_of("b-3") is None
        # B no puede leer texto de ids de A
        assert idx_b.text_of("a-7") is None

    # ------------------------------------------------------------------
    # d) Conteos por tenant
    # ------------------------------------------------------------------
    def test_count_is_per_tenant(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        assert idx_a.count() == 10
        assert idx_b.count() == 10

    def test_active_count_is_per_tenant(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        assert idx_a.active_count() == 10
        assert idx_b.active_count() == 10

    # ------------------------------------------------------------------
    # e) rebuild_from no borra otros tenants
    # ------------------------------------------------------------------
    def test_rebuild_from_does_not_delete_other_tenant(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)
        _populate(idx_a, idx_b)

        # Reconstruye solo A con 5 registros
        new_records = [_rec(f"a-new-{i}", f"nueva memoria {i}") for i in range(5)]
        idx_a.rebuild_from(new_records)

        # B sigue intacto
        assert idx_b.count() == 10
        # A tiene exactamente los 5 nuevos
        assert idx_a.count() == 5

    # ------------------------------------------------------------------
    # f) upsert guard: colisión de id entre tenants → ValueError
    # ------------------------------------------------------------------
    def test_upsert_guard_cross_tenant_id_collision_raises(self, tmp_path: Path) -> None:
        db = _shared_db(tmp_path)
        idx_a, idx_b = _make_pair(db)

        idx_a.upsert(_rec("shared-id", "memoria de A"))
        with pytest.raises(ValueError, match="tenant"):
            idx_b.upsert(_rec("shared-id", "intento de B de pisar a A"))

    # ------------------------------------------------------------------
    # g) Compat default: sin tenant kwarg → funciona como antes
    # ------------------------------------------------------------------
    def test_default_tenant_compat(self, tmp_path: Path) -> None:
        db = tmp_path / "default.db"
        emb = StubEmbedder(dim=64)
        idx = SqliteMemoryIndex(db, embedder=emb)
        idx.upsert(_rec("d-1", "memoria default"))
        assert idx.count() == 1
        assert idx.text_of("d-1") == "memoria default"
        result = idx.recall("memoria default")
        assert result is not None
