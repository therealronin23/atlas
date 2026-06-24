"""
Tests TDD para crypto-shredding f2-9: keystore separado + rebuild_from cifrado.

Criterios de aceptación:
  a) Keystore separado existe: tras upsert, fichero .keys existe y tiene la clave;
     la DB de records NO tiene claves en content_keys.
  b) Round-trip sigue OK: text_of(id) devuelve el plaintext original.
  c) rebuild_from cifra: la columna text no es plaintext; text_of descifra OK.
  d) shred sigue irrecuperable: ShreddedContentError + clave no está en keystore.
  e) Migración de DB legacy: filas en records.content_keys son migradas al keystore.
  f) close() cierra ambas conexiones sin lanzar.
"""

from __future__ import annotations

import sqlite3
import struct

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex, ShreddedContentError
from atlas.memory.record import GenericRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


class TestKeystoreSeparado:
    # ------------------------------------------------------------------
    # a) Keystore separado existe y DB de records no tiene claves
    # ------------------------------------------------------------------
    def test_keystore_file_exists_after_upsert(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("k1", "dato sensible"))
        keys_path = db.parent / (db.name + ".keys")
        assert keys_path.exists(), "El fichero .keys debe existir tras upsert"

    def test_keystore_has_the_key(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("k1", "dato sensible"))
        key = idx._get_key("k1")
        assert key is not None, "_get_key debe devolver la clave tras upsert"

    def test_records_db_has_no_keys(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("k1", "dato sensible"))
        count = idx._conn.execute("SELECT COUNT(*) FROM content_keys").fetchone()[0]
        assert count == 0, "La DB de records NO debe tener claves en content_keys"

    # ------------------------------------------------------------------
    # b) Round-trip sigue OK
    # ------------------------------------------------------------------
    def test_roundtrip_text_of_returns_plaintext(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("k2", "nombre: Ana Pérez"))
        assert idx.text_of("k2") == "nombre: Ana Pérez"

    # ------------------------------------------------------------------
    # c) rebuild_from cifra: columna text no es plaintext; text_of descifra OK
    # ------------------------------------------------------------------
    def test_rebuild_from_encrypts_text_column(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        plaintext = "rebuild secreto"
        idx.rebuild_from([_rec("r1", plaintext)])
        row = idx._conn.execute(
            "SELECT text FROM records WHERE id=?", ("r1",)
        ).fetchone()
        assert row is not None
        assert row[0] != plaintext, "rebuild_from debe cifrar; la columna no debe ser plaintext"

    def test_rebuild_from_text_of_decrypts_correctly(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.rebuild_from([_rec("r1", "rebuild secreto"), _rec("r2", "otro dato")])
        assert idx.text_of("r1") == "rebuild secreto"
        assert idx.text_of("r2") == "otro dato"

    # ------------------------------------------------------------------
    # d) shred sigue irrecuperable: ShreddedContentError + clave no en keystore
    # ------------------------------------------------------------------
    def test_shred_raises_shredded_content_error(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("s1", "borrar esto"))
        idx.shred("s1")
        with pytest.raises(ShreddedContentError):
            idx.text_of("s1")

    def test_shred_removes_key_from_keystore(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("s2", "borrar esto"))
        idx.shred("s2")
        assert idx._get_key("s2") is None, "La clave no debe estar en el keystore tras shred"

    # ------------------------------------------------------------------
    # e) Migración de DB legacy: filas en records.content_keys → keystore
    # ------------------------------------------------------------------
    def test_migrate_keystore_moves_keys_from_records_db(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        # Crear índice para que se cree el schema
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        # Insertar clave directamente en records.content_keys (simula estado legado)
        fake_key = b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        idx._conn.execute(
            "INSERT INTO content_keys (id, fernet_key) VALUES (?, ?)",
            ("legacy-key-1", fake_key),
        )
        idx._conn.commit()
        # Borrar del keystore para simular que sólo estaba en records
        idx._del_key("legacy-key-1")
        idx.close()

        # Reabrir: la migración debe trasladar la clave al keystore
        idx2 = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        # La clave debe haber sido migrada al keystore
        migrated = idx2._get_key("legacy-key-1")
        assert migrated == fake_key, "La clave debe haber sido migrada al keystore"
        # La DB de records no debe tener claves
        count = idx2._conn.execute("SELECT COUNT(*) FROM content_keys").fetchone()[0]
        assert count == 0, "Tras migración, records.content_keys debe estar vacía"
        idx2.close()

    # ------------------------------------------------------------------
    # f) close() cierra ambas conexiones sin lanzar
    # ------------------------------------------------------------------
    def test_close_does_not_raise(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("c1", "cierre limpio"))
        idx.close()
        # Verificar que ambas conexiones están cerradas intentando usarlas
        with pytest.raises(Exception):
            idx._conn.execute("SELECT 1")
        with pytest.raises(Exception):
            idx._keys_conn.execute("SELECT 1")
