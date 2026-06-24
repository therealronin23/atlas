"""
TDD tests para f2-13: keystore full-sweep — gc_keystore() barre TODAS las claves
huérfanas del keystore cuyo id NO existe en la tabla records.

Criterios de aceptación:
  a) Una clave huérfana directa (id que NO está en records) es borrada.
  b) Una clave de un id vivo permanece intacta.
  c) El round-trip de cifrado sigue funcionando tras gc_keystore().
  d) Idempotencia: 2ª llamada devuelve 0.
  e) shred sigue irrecuperable antes y después del GC.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex, ShreddedContentError
from atlas.memory.record import GenericRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


class TestGcKeystore:
    # ------------------------------------------------------------------
    # a+b) Huérfana directa desaparece; clave viva permanece
    # ------------------------------------------------------------------
    def test_orphan_key_removed_live_key_kept(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))

        # Insertar un record vivo con su clave
        idx.upsert(_rec("vivo", "contenido vivo"))

        # Sembrar una clave huérfana directamente en el keystore
        from cryptography.fernet import Fernet
        orphan_key = Fernet.generate_key()
        idx._put_key("huerfana-001", orphan_key)

        # Confirmar que la huérfana está en el keystore antes del GC
        assert idx._get_key("huerfana-001") is not None

        deleted = idx.gc_keystore()

        assert deleted == 1, "gc_keystore debe borrar exactamente 1 clave huérfana"
        assert idx._get_key("huerfana-001") is None, "La clave huérfana debe haber desaparecido"
        assert idx._get_key("vivo") is not None, "La clave del id vivo debe permanecer"

    # ------------------------------------------------------------------
    # c) Round-trip de cifrado sigue intacto
    # ------------------------------------------------------------------
    def test_roundtrip_intact_after_gc(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))

        idx.upsert(_rec("r1", "texto secreto"))

        from cryptography.fernet import Fernet
        idx._put_key("orphan-r", Fernet.generate_key())

        idx.gc_keystore()

        assert idx.text_of("r1") == "texto secreto"

    # ------------------------------------------------------------------
    # d) Idempotencia: 2ª llamada devuelve 0
    # ------------------------------------------------------------------
    def test_idempotent_second_call_returns_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))

        idx.upsert(_rec("v1", "vivo"))

        from cryptography.fernet import Fernet
        idx._put_key("ghost", Fernet.generate_key())

        first = idx.gc_keystore()
        assert first == 1

        second = idx.gc_keystore()
        assert second == 0, "2ª llamada debe devolver 0 (idempotente)"

    # ------------------------------------------------------------------
    # e) Múltiples huérfanas — todas borradas, count correcto
    # ------------------------------------------------------------------
    def test_multiple_orphans_all_removed(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))

        idx.upsert(_rec("live-a", "a"))
        idx.upsert(_rec("live-b", "b"))

        from cryptography.fernet import Fernet
        for orphan_id in ("x1", "x2", "x3"):
            idx._put_key(orphan_id, Fernet.generate_key())

        deleted = idx.gc_keystore()

        assert deleted == 3
        for orphan_id in ("x1", "x2", "x3"):
            assert idx._get_key(orphan_id) is None
        assert idx._get_key("live-a") is not None
        assert idx._get_key("live-b") is not None

    # ------------------------------------------------------------------
    # f) gc_keystore con keystore completamente limpio devuelve 0
    # ------------------------------------------------------------------
    def test_empty_keystore_returns_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("solo", "x"))
        # No sembramos huérfanas
        assert idx.gc_keystore() == 0

    # ------------------------------------------------------------------
    # g) shred sigue irrecuperable (smoke de integración post-GC)
    # ------------------------------------------------------------------
    def test_shred_irrecoverable_after_gc(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))

        idx.upsert(_rec("s1", "borrar"))

        from cryptography.fernet import Fernet
        idx._put_key("orphan-s", Fernet.generate_key())

        idx.shred("s1")
        idx.gc_keystore()

        with pytest.raises(ShreddedContentError):
            idx.text_of("s1")
