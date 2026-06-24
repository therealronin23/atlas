"""
TDD tests para dos items de backlog:
  - f2-10: keystore-orphan-gc — rebuild_from limpia claves huérfanas
  - f2-12: supersede-provenance — supersede acepta/propaga procedencia
"""

from __future__ import annotations

import hashlib
import time

import pytest
from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import (
    ProvenanceWriteGate,
    SqliteMemoryIndex,
    WriteRejected,
)
from atlas.memory.record import GenericRecord
from atlas.mcp.memory_trunk import MemoryTrunk


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


def _gated_index(db: Path) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64), write_gate=ProvenanceWriteGate())


# ============================================================
# Item A — f2-10: keystore-orphan-gc
# ============================================================


class TestKeystoreOrphanGC:
    def test_orphan_key_removed_after_rebuild(self, tmp_path: Path) -> None:
        """Un id borrado durante rebuild_from NO debe conservar su clave en el keystore."""
        db = tmp_path / "gc.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        # Insertar dos records
        idx.upsert(_rec("old-id", "texto viejo"))
        idx.upsert(_rec("keep-id", "texto nuevo"))
        # Verificar que old-id tiene clave
        assert idx._get_key("old-id") is not None

        # rebuild_from con sólo keep-id (old-id desaparece)
        idx.rebuild_from([_rec("keep-id", "texto nuevo")])

        # La clave de old-id debe haber sido eliminada del keystore
        assert idx._get_key("old-id") is None, (
            "rebuild_from debe eliminar claves de ids que ya no están en el índice"
        )

    def test_kept_key_still_present_after_rebuild(self, tmp_path: Path) -> None:
        """Un id que sí persiste en el rebuild debe conservar su clave (nueva generada)."""
        db = tmp_path / "gc2.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("keep-id", "texto"))

        idx.rebuild_from([_rec("keep-id", "texto")])

        assert idx._get_key("keep-id") is not None, (
            "El id que sigue en el índice debe tener clave en el keystore"
        )

    def test_roundtrip_after_rebuild_with_gc(self, tmp_path: Path) -> None:
        """text_of sigue funcionando tras un rebuild con GC."""
        db = tmp_path / "gc3.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("a", "alfa"))
        idx.upsert(_rec("b", "beta"))

        idx.rebuild_from([_rec("a", "alfa")])

        assert idx.text_of("a") == "alfa"

    def test_shred_still_works_after_rebuild_with_gc(self, tmp_path: Path) -> None:
        """shred sigue siendo irrecuperable tras un rebuild con GC."""
        from atlas.memory.memory_index import ShreddedContentError

        db = tmp_path / "gc4.db"
        idx = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        idx.rebuild_from([_rec("s1", "secreto")])
        idx.shred("s1")
        with pytest.raises(ShreddedContentError):
            idx.text_of("s1")
        assert idx._get_key("s1") is None


# ============================================================
# Item B — f2-12: supersede-provenance
# ============================================================


class TestSupersedePropagatesProvenance:
    def test_supersede_rejected_without_provenance_under_gate(self, tmp_path: Path) -> None:
        """Bajo ProvenanceWriteGate, index.supersede sin provenance falla (estado previo al fix)."""
        db = tmp_path / "sp0.db"
        # Primero insertar el old record sin gate para tener algo que superseder
        idx_plain = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        provenance = hashlib.sha256(b"old text0").hexdigest()
        idx_plain.upsert(_rec("old-0", "old text0"), merkle_leaf_hash=provenance)
        idx_plain.close()

        # Reabrir con gate
        idx = _gated_index(db)
        # Con el fix, supersede SIN provenance explícita DEBE fallar (gate rechaza)
        with pytest.raises(WriteRejected):
            idx.supersede("old-0", _rec("new-0", "new text0"))
        idx.close()

    def test_supersede_with_provenance_accepted_under_gate(self, tmp_path: Path) -> None:
        """index.supersede con merkle_leaf_hash explícito entra bajo ProvenanceWriteGate."""
        db = tmp_path / "sp1.db"
        idx_plain = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        old_prov = hashlib.sha256(b"old text1").hexdigest()
        idx_plain.upsert(_rec("old-1", "old text1"), merkle_leaf_hash=old_prov)
        idx_plain.close()

        idx = _gated_index(db)
        new_prov = hashlib.sha256(b"new text1").hexdigest()
        # No debe lanzar WriteRejected
        idx.supersede("old-1", _rec("new-1", "new text1"), merkle_leaf_hash=new_prov)
        assert idx.merkle_leaf_hash("new-1") == new_prov
        idx.close()

    def test_supersede_preserves_lineage(self, tmp_path: Path) -> None:
        """El lineage supersedes queda grabado en el nuevo record."""
        db = tmp_path / "sp2.db"
        idx_plain = SqliteMemoryIndex(db, embedder=StubEmbedder(dim=64))
        old_prov = hashlib.sha256(b"viejo").hexdigest()
        idx_plain.upsert(_rec("v1", "viejo"), merkle_leaf_hash=old_prov)
        idx_plain.close()

        idx = _gated_index(db)
        new_prov = hashlib.sha256(b"nuevo").hexdigest()
        idx.supersede("v1", _rec("v2", "nuevo"), merkle_leaf_hash=new_prov)
        assert idx.supersedes_of("v2") == "v1"
        idx.close()

    def test_trunk_supersede_generates_provenance(self, tmp_path: Path) -> None:
        """MemoryTrunk.supersede genera procedencia igual que add y entra bajo gate."""
        db = tmp_path / "sp3.db"
        idx = _gated_index(db)
        trunk = MemoryTrunk(idx)

        # Primero add el old record (con provenance generada por trunk.add)
        old_id = trunk.add("memoria original")

        # supersede a través del trunk: debe generar provenance y no ser rechazado
        new_id = trunk.supersede(old_id, "memoria actualizada")

        # El nuevo record tiene merkle_leaf_hash no None
        assert idx.merkle_leaf_hash(new_id) is not None
        assert len(idx.merkle_leaf_hash(new_id)) == 64  # type: ignore[arg-type]

    def test_trunk_supersede_preserves_lineage(self, tmp_path: Path) -> None:
        """MemoryTrunk.supersede con gate: lineage supersedes queda grabado."""
        db = tmp_path / "sp4.db"
        idx = _gated_index(db)
        trunk = MemoryTrunk(idx)

        old_id = trunk.add("base")
        new_id = trunk.supersede(old_id, "actualizado")

        assert idx.supersedes_of(new_id) == old_id
