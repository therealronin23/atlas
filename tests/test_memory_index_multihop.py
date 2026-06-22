"""
Tests TDD para SqliteMemoryIndex.recall_multihop.

El criterio central (a) demuestra que recall_multihop alcanza una memoria C
que NO es alcanzable con un único recall desde la query original. El embedder
StubEmbedder es bag-of-words hash: textos que comparten palabras producen
vectores similares.

Diseño del grafo semántico:
  query_A  → muy similar a A (comparten las palabras "alpha zeta foxtrot")
  A        → comparte con B palabras "bravo charlie" (únicas de A–B)
  B        → comparte con C palabras "delta echo" (únicas de B–C)
  C        → palabras "golf hotel india" (sin solapamiento directo con query_A)

Con threshold bajo (0.1) se garantiza que los hops encadenan. Con threshold
alto (0.99) se bloquea el salto y el test de borde lo verifica.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Textos diseñados para el grafo A→B→C con StubEmbedder:
#   query_A ≈ A  (comparten "alpha zeta foxtrot")
#   A ≈ B       (A añade "bravo charlie"; B = "bravo charlie delta echo")
#   B ≈ C       (B añade "delta echo";    C = "delta echo golf hotel india")
#   query_A NOT ≈ C (C no comparte palabras con query_A)

_TEXT_A = "alpha zeta foxtrot bravo charlie"
_TEXT_B = "bravo charlie delta echo"
_TEXT_C = "delta echo golf hotel india"
_QUERY_A = "alpha zeta foxtrot"


def _build_index(tmp_path: Path, threshold: float = 0.1) -> SqliteMemoryIndex:
    idx = SqliteMemoryIndex(
        tmp_path / "multi.db",
        embedder=StubEmbedder(dim=64),
        threshold=threshold,
    )
    idx.upsert(GenericRecord("mem_a", _TEXT_A))
    idx.upsert(GenericRecord("mem_b", _TEXT_B))
    idx.upsert(GenericRecord("mem_c", _TEXT_C))
    return idx


# ---------------------------------------------------------------------------
# (a) Criterio central: C NO alcanzable en 1 hop, SÍ en multi-hop
# ---------------------------------------------------------------------------


class TestMultihopCore:
    def test_c_not_reachable_in_one_hop(self, tmp_path: Path) -> None:
        """Un solo recall desde query_A no debe devolver mem_c."""
        idx = _build_index(tmp_path)
        result = idx.recall(_QUERY_A)
        assert result is not None and result.matched
        assert result.lesson_id != "mem_c", (
            "mem_c NO debe ser la respuesta directa a query_A"
        )

    def test_chain_reaches_c_in_multihop(self, tmp_path: Path) -> None:
        """recall_multihop(query_A, hops=3) debe devolver la cadena hasta mem_c."""
        idx = _build_index(tmp_path)
        chain = idx.recall_multihop(_QUERY_A, hops=3)
        assert len(chain) >= 2, "Debe encadenar al menos 2 hops"
        ids = [r.lesson_id for r in chain]
        assert "mem_c" in ids, (
            f"mem_c debe estar en la cadena multi-hop; cadena obtenida: {ids}"
        )

    def test_single_recall_does_not_reach_c(self, tmp_path: Path) -> None:
        """Confirma explícitamente que recall normal (1 hop) no llega a C."""
        idx = _build_index(tmp_path)
        single = idx.recall(_QUERY_A)
        multi = idx.recall_multihop(_QUERY_A, hops=3)
        single_id = single.lesson_id if single and single.matched else None
        multi_ids = [r.lesson_id for r in multi]
        assert single_id != "mem_c"
        assert "mem_c" in multi_ids


# ---------------------------------------------------------------------------
# (b) Sin repetición de ids en la cadena
# ---------------------------------------------------------------------------


class TestNoRepetition:
    def test_no_repeated_ids(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        chain = idx.recall_multihop(_QUERY_A, hops=3)
        ids = [r.lesson_id for r in chain]
        assert len(ids) == len(set(ids)), f"IDs repetidos en la cadena: {ids}"


# ---------------------------------------------------------------------------
# (c) hops=1 se comporta como recall simple
# ---------------------------------------------------------------------------


class TestSingleHop:
    def test_hops_1_equals_recall(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        single_recall = idx.recall(_QUERY_A)
        chain = idx.recall_multihop(_QUERY_A, hops=1)
        assert len(chain) == 1
        assert chain[0].lesson_id == single_recall.lesson_id  # type: ignore[union-attr]

    def test_hops_1_matched_required(self, tmp_path: Path) -> None:
        """Con threshold muy alto (0.99), recall no hace match → cadena vacía."""
        idx = _build_index(tmp_path, threshold=0.99)
        chain = idx.recall_multihop(_QUERY_A, hops=1)
        assert chain == []


# ---------------------------------------------------------------------------
# (d) hops <= 0 y query vacía → []
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_hops_zero_returns_empty(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        assert idx.recall_multihop(_QUERY_A, hops=0) == []

    def test_hops_negative_returns_empty(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        assert idx.recall_multihop(_QUERY_A, hops=-1) == []

    def test_empty_query_returns_empty(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        assert idx.recall_multihop("", hops=3) == []

    def test_whitespace_query_returns_empty(self, tmp_path: Path) -> None:
        idx = _build_index(tmp_path)
        assert idx.recall_multihop("   ", hops=3) == []


# ---------------------------------------------------------------------------
# (e) Índice vacío → []
# ---------------------------------------------------------------------------


class TestEmptyIndex:
    def test_empty_index_returns_empty(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(
            tmp_path / "empty.db",
            embedder=StubEmbedder(dim=64),
            threshold=0.1,
        )
        assert idx.recall_multihop("cualquier cosa", hops=3) == []
