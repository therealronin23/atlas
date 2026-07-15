"""
Regresiones de la auditoría pre-merge (2026-06-21) del sustrato de memoria.

Cada test fija un fallo encontrado y corregido:
- DIM-GUARD: reabrir el índice con un embedder de otra dim daba scores basura en
  silencio (el coseno truncaba vectores). Ahora falla ruidoso.
- SUPERSEDE robusto: old_id inexistente o nuevo id colisionante dejaban lineage
  corrupto/silencioso. Ahora lanza.
- MIGRACIÓN: filas de un esquema pre-1d quedaban con tier NULL (invisibles a
  tiers). Ahora se rellenan a hot/vigente.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder, embedding_identity_fingerprint
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t")


# ---------------------------------------------------------------------------
# DIM-GUARD
# ---------------------------------------------------------------------------


class TestDimGuard:
    def test_reopen_same_dim_ok(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("r1", "algo"))
        idx.close()
        reopened = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))  # mismo dim
        assert reopened.count() == 1

    def test_reopen_wrong_dim_raises(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("r1", "algo"))
        idx.close()
        with pytest.raises(ValueError, match="dim mismatch"):
            SqliteMemoryIndex(db, embedder=StubEmbedder(dim=32))


# ---------------------------------------------------------------------------
# SUPERSEDE robusto
# ---------------------------------------------------------------------------


class TestSupersedeGuards:
    def test_supersede_missing_old_raises(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        with pytest.raises(KeyError):
            idx.supersede("ghost", _rec("new", "x"), now_ns=1)

    def test_supersede_colliding_new_id_raises(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("old", "viejo"))
        idx.upsert(_rec("dup", "otro"))
        with pytest.raises(ValueError, match="ya existe"):
            idx.supersede("old", _rec("dup", "nuevo"), now_ns=1)


# ---------------------------------------------------------------------------
# MIGRACIÓN desde esquema pre-1d
# ---------------------------------------------------------------------------


class TestMigrationBackfill:
    def test_pre_1d_rows_get_tier_and_stay_active(self, tmp_path: Path) -> None:
        db = tmp_path / "legacy.db"
        # Construye a mano el esquema PRE-1d (sin columnas temporales). Para
        # permitir la migración de una fila vectorial heredada aportamos prueba
        # explícita del espacio que la generó; sin ella el motor falla cerrado.
        con = sqlite3.connect(str(db))
        con.execute(
            "CREATE TABLE records (ordinal INTEGER PRIMARY KEY AUTOINCREMENT, "
            "id TEXT UNIQUE NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL, "
            "merkle_leaf_hash TEXT, merkle_leaf_index INTEGER, created_at TEXT)"
        )
        vec = StubEmbedder(dim=64).embed("dato heredado")
        blob = struct.pack(f"<{len(vec)}d", *vec)
        con.execute(
            "INSERT INTO records (id, text, vector, created_at) VALUES (?,?,?,?)",
            ("legacy-1", "dato heredado", blob, "t"),
        )
        identity = StubEmbedder(dim=64).identity
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        con.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (
                ("embedder_identity", identity),
                ("embedder_fingerprint", embedding_identity_fingerprint(identity)),
            ),
        )
        con.commit()
        con.close()

        # Abrir con el motor actual → migra + backfill, sin perder la fila.
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        assert idx.count() == 1
        assert idx.active_count() == 1
        assert idx.tier("legacy-1") == "hot"
        assert idx.tier_counts().get("hot") == 1
        res = idx.recall("dato heredado")
        assert res is not None and res.lesson_id == "legacy-1"
