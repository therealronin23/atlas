"""
tests/test_memory_index.py — Tests TDD para retrieval híbrido (BM25 léxico + coseno + RRF).

Cubre:
  - lexical_index=False (default): sin records_fts, recall_lexical lanza RuntimeError.
  - lexical_index=True: crea records_fts, recall_lexical encuentra por término exacto.
  - Query con guiones (escape OK, sin excepción de sintaxis FTS).
  - Shred de un record elimina su fila de records_fts.
  - rrf_fuse: función pura de fusión RRF.
  - Fusión coseno+léxico devuelve resultados.
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path

from atlas.memory.memory_index import SqliteMemoryIndex, rrf_fuse
from atlas.memory.record import GenericRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text)


def _open_idx(tmp_path: Path, lexical_index: bool = False) -> SqliteMemoryIndex:
    db = tmp_path / "test.db"
    return SqliteMemoryIndex(db, lexical_index=lexical_index)


# ---------------------------------------------------------------------------
# lexical_index=False (default): sin cambio de esquema, RuntimeError en recall_lexical
# ---------------------------------------------------------------------------

class TestLexicalIndexOff:
    def test_default_is_false(self, tmp_path: Path) -> None:
        """Constructor sin lexical_index crea el índice en modo OFF."""
        idx = _open_idx(tmp_path)
        # No debe existir records_fts
        tables = {
            row[0]
            for row in idx._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "records_fts" not in tables

    def test_recall_lexical_raises_runtime_error(self, tmp_path: Path) -> None:
        idx = _open_idx(tmp_path)
        idx.upsert(_make_record("r1", "hola mundo"))
        with pytest.raises(RuntimeError, match="lexical_index"):
            idx.recall_lexical("hola")

    def test_upsert_and_recall_all_unchanged(self, tmp_path: Path) -> None:
        """Comportamiento coseno intacto cuando lexical_index=False."""
        idx = _open_idx(tmp_path)
        idx.upsert(_make_record("r1", "Python usa indentacion"))
        results = idx.recall_all("Python indentacion", k=5)
        assert len(results) == 1
        assert results[0].lesson_id == "r1"


# ---------------------------------------------------------------------------
# lexical_index=True: crea records_fts y recall_lexical funciona
# ---------------------------------------------------------------------------

class TestLexicalIndexOn:
    def test_records_fts_table_created(self, tmp_path: Path) -> None:
        idx = _open_idx(tmp_path, lexical_index=True)
        tables = {
            row[0]
            for row in idx._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' OR type='shadow'"
            ).fetchall()
        }
        assert "records_fts" in tables

    def test_idempotent_init(self, tmp_path: Path) -> None:
        """Reabrir el índice con lexical_index=True no lanza excepción."""
        db = tmp_path / "idx.db"
        idx1 = SqliteMemoryIndex(db, lexical_index=True)
        idx1.upsert(_make_record("r1", "texto de prueba SRV-4471"))
        idx1.close()
        idx2 = SqliteMemoryIndex(db, lexical_index=True)
        results = idx2.recall_lexical("SRV-4471")
        assert any(r.lesson_id == "r1" for r in results)

    def test_recall_lexical_finds_rare_term(self, tmp_path: Path) -> None:
        """recall_lexical encuentra un id raro que el coseno probablemente no encontraria."""
        idx = _open_idx(tmp_path, lexical_index=True)
        idx.upsert(_make_record("r-rare", "error de sistema SRV-4471 en produccion"))
        idx.upsert(_make_record("r-other", "Python usa indentacion para bloques"))
        results = idx.recall_lexical("SRV-4471", k=5)
        ids = [r.lesson_id for r in results]
        assert "r-rare" in ids
        assert "r-other" not in ids

    def test_recall_lexical_query_with_dashes_does_not_raise(self, tmp_path: Path) -> None:
        """Query con guiones no explota la sintaxis FTS."""
        idx = _open_idx(tmp_path, lexical_index=True)
        idx.upsert(_make_record("r1", "codigo SRV-4471 en log"))
        # No debe lanzar excepciones
        results = idx.recall_lexical("SRV-4471", k=3)
        assert isinstance(results, list)

    def test_recall_lexical_returns_recall_results(self, tmp_path: Path) -> None:
        from atlas.immunity.lesson_recaller import RecallResult
        idx = _open_idx(tmp_path, lexical_index=True)
        idx.upsert(_make_record("r1", "hola mundo extrapalabra"))
        results = idx.recall_lexical("extrapalabra", k=5)
        assert all(isinstance(r, RecallResult) for r in results)
        assert all(r.matched is True for r in results)

    def test_recall_lexical_respects_tenant(self, tmp_path: Path) -> None:
        """Records de otro tenant no aparecen en recall_lexical del tenant actual."""
        db = tmp_path / "idx.db"
        idx_a = SqliteMemoryIndex(db, tenant="A", lexical_index=True)
        idx_b = SqliteMemoryIndex(db, tenant="B", lexical_index=True)
        idx_a.upsert(_make_record("a1", "token secreto XQZT9988"))
        # Tenant B no debe ver XQZT9988
        results = idx_b.recall_lexical("XQZT9988", k=5)
        assert all(r.lesson_id != "a1" for r in results)

    def test_recall_lexical_ignores_superseded(self, tmp_path: Path) -> None:
        """Records con valid_until_ns (superseded) no aparecen en recall_lexical."""
        idx = _open_idx(tmp_path, lexical_index=True)
        idx.upsert(_make_record("old", "texto RARO-9999 viejo"))
        idx.retire("old", reason="test")
        results = idx.recall_lexical("RARO-9999", k=5)
        assert all(r.lesson_id != "old" for r in results)


# ---------------------------------------------------------------------------
# Shred: la fila FTS desaparece tras el shred
# ---------------------------------------------------------------------------

class TestShredSyncFts:
    def test_shred_removes_fts_row(self, tmp_path: Path) -> None:
        idx = _open_idx(tmp_path, lexical_index=True)
        idx.upsert(_make_record("victim", "datos criticos TOKEN-8877"))
        # Verificar que está en FTS antes
        pre = idx._conn.execute(
            "SELECT rowid FROM records_fts WHERE records_fts MATCH ?",
            ('"TOKEN-8877"',),
        ).fetchall()
        assert len(pre) >= 1

        idx.shred("victim")

        # Tras shred NO debe quedar la fila en records_fts
        post = idx._conn.execute(
            "SELECT rowid FROM records_fts WHERE records_fts MATCH ?",
            ('"TOKEN-8877"',),
        ).fetchall()
        assert len(post) == 0

    def test_shred_on_non_lexical_index_still_works(self, tmp_path: Path) -> None:
        """shred sobre índice sin FTS sigue funcionando como antes."""
        idx = _open_idx(tmp_path, lexical_index=False)
        idx.upsert(_make_record("r1", "texto normal"))
        idx.shred("r1")  # no debe lanzar


# ---------------------------------------------------------------------------
# rrf_fuse: función pura
# ---------------------------------------------------------------------------

class TestRrfFuse:
    def test_consensus_rises(self) -> None:
        """Un id que aparece en todas las listas debe estar arriba."""
        rankings = [
            ["a", "b", "c"],
            ["b", "a", "d"],
            ["b", "c", "a"],
        ]
        result = rrf_fuse(rankings, k=60)
        # "b" aparece #1, #2, #1 → consenso fuerte
        # "a" aparece #2, #1, #3 → también alto
        assert result[0] in {"a", "b"}, f"top inesperado: {result[0]}"
        # Ambos a y b deben estar en top-2
        assert set(result[:2]) == {"a", "b"}

    def test_rrf_classic_two_lists(self) -> None:
        """RRF clásico: score(r, k) = sum(1/(k+rank_i))."""
        # Lista A: [x, y], Lista B: [y, x]
        # x: 1/(60+1) + 1/(60+2) = 1/61 + 1/62
        # y: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 — igual → empate
        rankings = [["x", "y"], ["y", "x"]]
        result = rrf_fuse(rankings, k=60)
        assert set(result) == {"x", "y"}

    def test_single_ranking_preserves_order(self) -> None:
        rankings = [["a", "b", "c", "d"]]
        result = rrf_fuse(rankings, k=60)
        assert result == ["a", "b", "c", "d"]

    def test_empty_rankings(self) -> None:
        assert rrf_fuse([], k=60) == []

    def test_empty_inner_list(self) -> None:
        result = rrf_fuse([[], ["a", "b"]], k=60)
        assert result == ["a", "b"]

    def test_returns_all_unique_ids(self) -> None:
        rankings = [["a", "b"], ["b", "c"]]
        result = rrf_fuse(rankings)
        assert sorted(result) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# recall_temporal — Palanca F3: validez temporal + recencia
# ---------------------------------------------------------------------------

class TestRecallTemporal:
    """Tests TDD para recall_temporal (Fase F3)."""

    def _open_idx(self, tmp_path: Path, tenant: str = "default") -> SqliteMemoryIndex:
        db = tmp_path / "temporal.db"
        return SqliteMemoryIndex(db, tenant=tenant)

    # ------------------------------------------------------------------
    # AS-OF en el pasado: devuelve la versión que era válida entonces
    # ------------------------------------------------------------------

    def test_asof_past_returns_old_version(self, tmp_path: Path) -> None:
        """as_of_ns en el pasado recupera la versión vigente en ese instante,
        aunque hoy esté superseded por una versión más nueva."""
        idx = self._open_idx(tmp_path)

        t0 = 1_000_000_000_000_000_000  # t=1 s en ns (instante base)
        t1 = t0 + 1_000_000_000         # t=2 s (1 segundo después)
        t2 = t0 + 2_000_000_000         # t=3 s (2 segundos después)

        # Insertar directamente para controlar valid_from/until.
        from atlas.memory.memory_index import _pack
        from atlas.memory.embeddings import StubEmbedder
        emb = StubEmbedder(dim=64)
        v_old = emb.embed("Python es lento")
        v_new = emb.embed("Python es rapido")
        from cryptography.fernet import Fernet
        # Insertar v1 (vigente t0 -> t1) y v2 (vigente t1 -> NULL).
        key1 = Fernet.generate_key()
        tok1 = Fernet(key1).encrypt("Python es lento".encode()).decode()
        key2 = Fernet.generate_key()
        tok2 = Fernet(key2).encrypt("Python es rapido".encode()).decode()
        idx._conn.execute("DELETE FROM records")  # limpiar filas previas del upsert fallido
        idx._conn.execute(
            "INSERT INTO records (id, text, vector, valid_from_ns, valid_until_ns, "
            "tier, last_access_ns, access_count, shredded, tenant, memory_class) "
            "VALUES (?, ?, ?, ?, ?, 'hot', ?, 0, 0, 'default', 'factual')",
            ("v1", tok1, _pack(v_old), t0, t1, t0),
        )
        idx._keys_conn.execute(
            "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)", ("v1", key1)
        )
        idx._conn.execute(
            "INSERT INTO records (id, text, vector, valid_from_ns, valid_until_ns, "
            "tier, last_access_ns, access_count, shredded, tenant, memory_class) "
            "VALUES (?, ?, ?, ?, NULL, 'hot', ?, 0, 0, 'default', 'factual')",
            ("v2", tok2, _pack(v_new), t1, t1),
        )
        idx._keys_conn.execute(
            "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)", ("v2", key2)
        )
        idx._conn.commit()
        idx._keys_conn.commit()

        # as_of = t0 + 0.5 s → solo v1 era válido (v2 todavía no había entrado).
        as_of_past = t0 + 500_000_000  # mitad del intervalo de v1
        results_past = idx.recall_temporal("Python", as_of_ns=as_of_past)
        ids_past = [r.lesson_id for r in results_past]
        assert "v1" in ids_past, f"v1 debía aparecer as_of pasado, got {ids_past}"
        assert "v2" not in ids_past, f"v2 no debía aparecer as_of pasado, got {ids_past}"

        # as_of = t2 (después de t1) → solo v2 es válido (v1 ya expiró en t1).
        results_now = idx.recall_temporal("Python", as_of_ns=t2)
        ids_now = [r.lesson_id for r in results_now]
        assert "v2" in ids_now, f"v2 debía aparecer as_of t2, got {ids_now}"
        assert "v1" not in ids_now, f"v1 no debía aparecer as_of t2, got {ids_now}"

    # ------------------------------------------------------------------
    # Recencia: con half_life_ns, el record más reciente rankea primero
    # ------------------------------------------------------------------

    def test_recency_boost_with_half_life(self, tmp_path: Path) -> None:
        """Con half_life_ns dado, el record con valid_from_ns más reciente sube en ranking."""
        from atlas.memory.memory_index import _pack
        from atlas.memory.embeddings import StubEmbedder
        from cryptography.fernet import Fernet

        idx = self._open_idx(tmp_path)
        emb = StubEmbedder(dim=64)

        # Fijamos manualmente vectores idénticos para que el coseno sea igual.
        # El único diferenciador es valid_from_ns.
        t_base = 1_000_000_000_000_000_000
        half_life = 1_000_000_000  # 1 segundo

        # Usamos el mismo texto para ambos → mismo vector coseno.
        text = "memoria temporal importante"
        vec = emb.embed(text)

        for i, vfrom in enumerate([t_base, t_base + 2 * half_life]):
            key = Fernet.generate_key()
            tok = Fernet(key).encrypt(text.encode()).decode()
            rid = f"r{i}"
            idx._conn.execute(
                "INSERT INTO records (id, text, vector, valid_from_ns, valid_until_ns, "
                "tier, last_access_ns, access_count, shredded, tenant, memory_class) "
                "VALUES (?, ?, ?, ?, NULL, 'hot', ?, 0, 0, 'default', 'factual')",
                (rid, tok, _pack(vec), vfrom, vfrom),
            )
            idx._keys_conn.execute(
                "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)", (rid, key)
            )
        idx._conn.commit()
        idx._keys_conn.commit()

        # as_of = t_base + 4 * half_life → r1 (más reciente) tiene menor age → mayor score.
        as_of = t_base + 4 * half_life
        results = idx.recall_temporal(text, k=10, as_of_ns=as_of, half_life_ns=half_life)
        ids = [r.lesson_id for r in results]
        assert len(ids) == 2
        # r1 tiene valid_from = t_base + 2*half_life → age = 2*half → score *= 0.25
        # r0 tiene valid_from = t_base → age = 4*half → score *= 0.0625
        # r1 debe estar primero.
        assert ids[0] == "r1", f"r1 (más reciente) debía rankear primero, got {ids}"

    # ------------------------------------------------------------------
    # as_of=None usa ahora: excluye futuros y superseded
    # ------------------------------------------------------------------

    def test_asof_none_excludes_future_and_superseded(self, tmp_path: Path) -> None:
        """as_of=None usa time.time_ns(): excluye records cuyo valid_from está en el futuro
        y records con valid_until_ns ya establecido (superseded/retired)."""
        from atlas.memory.memory_index import _pack
        from atlas.memory.embeddings import StubEmbedder
        from cryptography.fernet import Fernet

        idx = self._open_idx(tmp_path)
        emb = StubEmbedder(dim=64)

        now = time.time_ns()
        past = now - 10_000_000_000   # 10 s antes
        future = now + 10_000_000_000  # 10 s después

        text = "hecho temporal"
        vec = emb.embed(text)

        entries = [
            # (rid, valid_from_ns, valid_until_ns)
            ("current", past, None),      # vigente
            ("future", future, None),     # no válido aún
            ("expired", past, now - 1),   # ya expirado (superseded)
        ]
        for rid, vfrom, vuntil in entries:
            key = Fernet.generate_key()
            tok = Fernet(key).encrypt(text.encode()).decode()
            idx._conn.execute(
                "INSERT INTO records (id, text, vector, valid_from_ns, valid_until_ns, "
                "tier, last_access_ns, access_count, shredded, tenant, memory_class) "
                "VALUES (?, ?, ?, ?, ?, 'hot', ?, 0, 0, 'default', 'factual')",
                (rid, tok, _pack(vec), vfrom, vuntil, vfrom),
            )
            idx._keys_conn.execute(
                "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)", (rid, key)
            )
        idx._conn.commit()
        idx._keys_conn.commit()

        results = idx.recall_temporal(text)  # as_of=None → ahora
        ids = {r.lesson_id for r in results}
        assert "current" in ids, "current debía aparecer"
        assert "future" not in ids, "future no debía aparecer (aún no válido)"
        assert "expired" not in ids, "expired no debía aparecer (ya caducado)"

    # ------------------------------------------------------------------
    # Respeto de tenant
    # ------------------------------------------------------------------

    def test_temporal_respects_tenant(self, tmp_path: Path) -> None:
        """Un record de otro tenant no aparece en recall_temporal del tenant actual."""
        db = tmp_path / "multitenant.db"
        idx_a = SqliteMemoryIndex(db, tenant="A")
        idx_b = SqliteMemoryIndex(db, tenant="B")

        rec_a = _make_record("secret_a", "dato exclusivo tenant A")
        idx_a.upsert(rec_a)

        results = idx_b.recall_temporal("dato exclusivo tenant A")
        ids = {r.lesson_id for r in results}
        assert "secret_a" not in ids, "record de tenant A no debe aparecer en tenant B"
