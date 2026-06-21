"""
Tests del MOTOR genérico de memoria (SqliteMemoryIndex + MemoryAbstractor).

Prueba la AGNOSTICIDAD de dominio: el motor opera sobre `GenericRecord` de un
dominio que NO es ciberseguridad (notas de cocina), sin conocer lecciones,
stances ni Garak. Si esto pasa, "el motor es genérico" deja de ser una
afirmación sin respaldo y queda demostrada.
"""

from __future__ import annotations

from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_abstractor import MemoryAbstractor
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord, MemoryRecord


def _recipes() -> list[GenericRecord]:
    return [
        GenericRecord("r1", "tortilla de patata huevo cebolla aceite", record_type="episodic"),
        GenericRecord("r2", "huevo cebolla aceite patata tortilla", record_type="episodic"),  # reorden
        GenericRecord("r3", "tarta de manzana harina azucar canela horno", record_type="episodic"),
    ]


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------


def test_generic_record_satisfies_protocol() -> None:
    rec = GenericRecord("x", "texto", created_at="t", record_type="analytic")
    assert isinstance(rec, MemoryRecord)


# ---------------------------------------------------------------------------
# Índice genérico, dominio no-seguridad
# ---------------------------------------------------------------------------


class TestGenericIndex:
    def test_recall_in_non_security_domain(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64), threshold=0.8)
        idx.rebuild_from(_recipes())
        assert idx.count() == 3
        # Reformulación de la tortilla → casa con r1/r2, no con la tarta.
        res = idx.recall("patata cebolla huevo aceite tortilla")
        assert res is not None and res.matched
        assert res.lesson_id in {"r1", "r2"}

    def test_persists_and_links_merkle_leaf(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_recipes()[0], merkle_leaf_hash="cafe", merkle_leaf_index=3)
        assert idx.merkle_leaf_hash("r1") == "cafe"
        assert idx.merkle_leaf_index("r1") == 3


# ---------------------------------------------------------------------------
# Abstractor genérico, dominio no-seguridad
# ---------------------------------------------------------------------------


class TestGenericAbstractor:
    def test_clusters_by_similarity_across_domain(self, tmp_path: Path) -> None:
        abs = MemoryAbstractor(embedder=StubEmbedder(dim=64), threshold=0.8)
        patterns = abs.abstract(_recipes())
        # Las dos tortillas colapsan; la tarta queda aparte → 2 patrones.
        assert len(patterns) == 2
        sizes = sorted(p.n_examples for p in patterns)
        assert sizes == [1, 2]

    def test_recall_over_patterns_non_security(self, tmp_path: Path) -> None:
        abs = MemoryAbstractor(embedder=StubEmbedder(dim=64), threshold=0.8)
        patterns = abs.abstract(_recipes())
        match = abs.recall("tortilla aceite huevo patata cebolla")
        assert match is not None and match.matched
        tortilla_pattern = next(p for p in patterns if "r1" in p.member_ids)
        assert match.pattern_id == tortilla_pattern.id
