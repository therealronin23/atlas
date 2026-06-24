"""
Tests TDD para write-gating contra envenenamiento de memoria en SqliteMemoryIndex.

Criterios de aceptación:
  a) Sin gate (default): upsert sin provenance funciona igual que hoy (compat).
  b) ProvenanceWriteGate rechaza sin procedencia: lanza WriteRejected, count==0.
  c) ProvenanceWriteGate acepta con procedencia: inserta correctamente.
  d) AllowAllWriteGate: nunca rechaza aunque no haya provenance.
  e) Gate inyectable / política custom: rechaza texto con "POISON", acepta legítimo.
  f) WriteRejected es subclase de Exception con mensaje informativo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import (
    AllowAllWriteGate,
    ProvenanceWriteGate,
    SqliteMemoryIndex,
    WriteRejected,
)
from atlas.memory.record import GenericRecord, MemoryRecord


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="2026-06-24")


def _index(tmp_path: Path, **kwargs) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), **kwargs)


# ------------------------------------------------------------------
# a) Compatibilidad: sin gate, upsert sin provenance funciona
# ------------------------------------------------------------------
class TestNoGate:
    def test_upsert_without_provenance_works_by_default(self, tmp_path: Path) -> None:
        idx = _index(tmp_path)
        idx.upsert(_rec("r1", "texto legítimo"))
        assert idx.count() == 1

    def test_text_is_recoverable_without_gate(self, tmp_path: Path) -> None:
        idx = _index(tmp_path)
        idx.upsert(_rec("r1", "hola mundo"))
        assert idx.text_of("r1") == "hola mundo"


# ------------------------------------------------------------------
# b) ProvenanceWriteGate rechaza sin procedencia
# ------------------------------------------------------------------
class TestProvenanceWriteGateRejects:
    def test_upsert_without_hash_raises_write_rejected(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        with pytest.raises(WriteRejected):
            idx.upsert(_rec("r1", "memoria sin procedencia"))

    def test_rejected_record_is_not_indexed(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        try:
            idx.upsert(_rec("r1", "memoria sin procedencia"))
        except WriteRejected:
            pass
        assert idx.count() == 0

    def test_recall_does_not_find_rejected_record(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        try:
            idx.upsert(_rec("r1", "memoria sin procedencia"))
        except WriteRejected:
            pass
        results = idx.recall("memoria sin procedencia")
        assert results is None or len(results) == 0

    def test_empty_string_hash_is_rejected(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        with pytest.raises(WriteRejected):
            idx.upsert(_rec("r1", "texto"), merkle_leaf_hash="")

    def test_whitespace_only_hash_is_rejected(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        with pytest.raises(WriteRejected):
            idx.upsert(_rec("r1", "texto"), merkle_leaf_hash="   ")


# ------------------------------------------------------------------
# c) ProvenanceWriteGate acepta con procedencia
# ------------------------------------------------------------------
class TestProvenanceWriteGateAccepts:
    def test_upsert_with_valid_hash_inserts(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        idx.upsert(_rec("r1", "memoria verificada"), merkle_leaf_hash="abc123")
        assert idx.count() == 1

    def test_text_recoverable_after_accepted_upsert(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=ProvenanceWriteGate())
        idx.upsert(_rec("r1", "datos verificados"), merkle_leaf_hash="deadbeef")
        assert idx.text_of("r1") == "datos verificados"


# ------------------------------------------------------------------
# d) AllowAllWriteGate nunca rechaza
# ------------------------------------------------------------------
class TestAllowAllWriteGate:
    def test_allows_upsert_without_provenance(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=AllowAllWriteGate())
        idx.upsert(_rec("r1", "sin hash"))
        assert idx.count() == 1

    def test_allows_upsert_with_provenance(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=AllowAllWriteGate())
        idx.upsert(_rec("r2", "con hash"), merkle_leaf_hash="abc")
        assert idx.count() == 1


# ------------------------------------------------------------------
# e) Gate inyectable con política custom
# ------------------------------------------------------------------
class PoisonBlockGate:
    """Ejemplo de gate personalizado: rechaza memorias con 'POISON' en el texto."""

    def check(self, record: MemoryRecord, *, provenance: str | None) -> None:
        if "POISON" in record.text:
            raise WriteRejected(
                f"Memoria rechazada por política anti-envenenamiento: {record.record_id!r}"
            )


class TestCustomGatePolicy:
    def test_poison_text_is_rejected(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=PoisonBlockGate())
        with pytest.raises(WriteRejected):
            idx.upsert(_rec("evil", "POISON: inyección de memoria maliciosa"))

    def test_poison_record_not_indexed(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=PoisonBlockGate())
        try:
            idx.upsert(_rec("evil", "POISON inyección"))
        except WriteRejected:
            pass
        assert idx.count() == 0

    def test_legitimate_text_passes_custom_gate(self, tmp_path: Path) -> None:
        idx = _index(tmp_path, write_gate=PoisonBlockGate())
        idx.upsert(_rec("legit", "memoria completamente legítima"))
        assert idx.count() == 1


# ------------------------------------------------------------------
# f) WriteRejected es subclase de Exception con mensaje informativo
# ------------------------------------------------------------------
class TestWriteRejectedClass:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(WriteRejected, Exception)

    def test_message_is_informative(self) -> None:
        exc = WriteRejected("provenance es None: escritura rechazada para id='r1'")
        assert "r1" in str(exc)
        assert len(str(exc)) > 10
