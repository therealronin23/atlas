"""
Tests TDD para crypto-shredding (olvido irrecuperable de contenido) en SqliteMemoryIndex.

Criterios de aceptación:
  a) Round-trip: upsert → text_of devuelve el original.
  b) Cifrado en disco: la columna text NO es el plaintext.
  c) shred irrecuperable: text_of lanza ShreddedContentError, no queda clave.
  d) Merkle/slot intacto: merkle_leaf_hash/index iguales; count() no disminuye.
  e) recall tras cifrado: devuelve el match correcto.
  f) shred de id inexistente → KeyError.
  g) legacy plaintext: fila sin content_keys (shredded=0) → text_of devuelve texto.
"""

from __future__ import annotations

import struct

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex, ShreddedContentError
from atlas.memory.record import GenericRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


class TestCryptoShredding:
    # ------------------------------------------------------------------
    # a) Round-trip
    # ------------------------------------------------------------------
    def test_roundtrip_text_of_returns_plaintext(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("pii-1", "nombre: Juan García, DNI: 12345678A"))
        assert idx.text_of("pii-1") == "nombre: Juan García, DNI: 12345678A"

    # ------------------------------------------------------------------
    # b) Cifrado en disco
    # ------------------------------------------------------------------
    def test_text_column_is_not_plaintext(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("pii-2", "tarjeta: 4111111111111111"))
        row = idx._conn.execute(
            "SELECT text FROM records WHERE id=?", ("pii-2",)
        ).fetchone()
        assert row is not None
        assert row[0] != "tarjeta: 4111111111111111"

    # ------------------------------------------------------------------
    # c) shred irrecuperable
    # ------------------------------------------------------------------
    def test_shred_raises_shredded_content_error(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("pii-3", "email: test@example.com"))
        idx.shred("pii-3")
        with pytest.raises(ShreddedContentError):
            idx.text_of("pii-3")

    def test_shred_removes_key_from_keystore(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("pii-4", "phone: +34 600 000 000"))
        idx.shred("pii-4")
        row = idx._conn.execute(
            "SELECT fernet_key FROM content_keys WHERE id=?", ("pii-4",)
        ).fetchone()
        assert row is None

    # ------------------------------------------------------------------
    # d) Merkle/slot intacto tras shred
    # ------------------------------------------------------------------
    def test_shred_preserves_merkle_and_count(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(
            _rec("pii-5", "dirección: Calle Mayor 1"),
            merkle_leaf_hash="abc123",
            merkle_leaf_index=7,
        )
        before_count = idx.count()
        idx.shred("pii-5")
        assert idx.merkle_leaf_hash("pii-5") == "abc123"
        assert idx.merkle_leaf_index("pii-5") == 7
        assert idx.count() == before_count

    # ------------------------------------------------------------------
    # e) recall tras cifrado
    # ------------------------------------------------------------------
    def test_recall_returns_correct_match_after_encryption(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), threshold=0.5)
        idx.upsert(_rec("r1", "python seguridad inyección SQL"))
        idx.upsert(_rec("r2", "memoria cifrada con fernet"))
        idx.upsert(_rec("r3", "python seguridad inyección SQL"))
        result = idx.recall("python seguridad inyección SQL")
        assert result is not None
        assert result.matched
        assert result.lesson_id in {"r1", "r3"}

    # ------------------------------------------------------------------
    # f) shred de id inexistente → KeyError
    # ------------------------------------------------------------------
    def test_shred_nonexistent_raises_key_error(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        with pytest.raises(KeyError):
            idx.shred("no-existe")

    # ------------------------------------------------------------------
    # g) legacy plaintext: fila sin content_keys (shredded=0) → devuelve texto
    # ------------------------------------------------------------------
    def test_legacy_plaintext_row_returned_without_error(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        vec_bytes = struct.pack("<64d", *([0.1] * 64))
        idx._conn.execute(
            "INSERT INTO records (id, text, vector, shredded, tier, access_count) "
            "VALUES (?, ?, ?, 0, 'hot', 0)",
            ("legacy-1", "texto en claro legacy", vec_bytes),
        )
        idx._conn.commit()
        assert idx.text_of("legacy-1") == "texto en claro legacy"

    # ------------------------------------------------------------------
    # Extra: re-upsert del mismo id re-cifra y resetea shredded
    # ------------------------------------------------------------------
    def test_reupsert_same_id_works(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("pii-6", "original"))
        idx.upsert(_rec("pii-6", "actualizado"))
        assert idx.text_of("pii-6") == "actualizado"

    # ------------------------------------------------------------------
    # h) secure_delete pragma activo para sobrescritura física real
    # ------------------------------------------------------------------
    def test_secure_delete_pragma_enabled(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        # secure_delete debe estar activo para que el DELETE de la clave en shred
        # sobrescriba físicamente las páginas (olvido irrecuperable real, no solo a nivel API).
        value = idx._conn.execute("PRAGMA secure_delete").fetchone()[0]
        assert value == 1
