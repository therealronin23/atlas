"""
Tests de validez temporal + supersesión + olvido auditable (Fase 1d-a, sobre el motor).

Ataca el hueco #1 que el campo (Mem0/Zep/Letta) admite no resolver: staleness y
contradicciones. El sustrato verificable lo resuelve SIN borrar nada del log:
- una memoria vigente tiene `valid_until_ns IS NULL`; el recall solo surfacea vigentes.
- supersede(old→new): la vieja se marca caducada (valid_until=now) + `supersedes`, la
  nueva pasa a vigente. La vieja NO se borra: sigue en la tabla (auditable).
- retire(id): olvido sin reemplazo (caduca sin nueva). Tampoco borra.
- Con MerkleLogger, cada transición se ancla en cadena → se puede PROBAR qué era
  vigente y cuándo dejó de serlo. Eso es lo que nadie tiene.
"""

from __future__ import annotations

from pathlib import Path

from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _idx(tmp_path: Path, **kw) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), threshold=0.8, **kw)


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t", record_type="empirical")


# ---------------------------------------------------------------------------
# Vigencia por defecto
# ---------------------------------------------------------------------------


class TestCurrentByDefault:
    def test_new_record_is_current_and_recalled(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "eval user_input arbitrario"))
        res = idx.recall("eval user_input arbitrario")
        assert res is not None and res.lesson_id == "r1"
        assert idx.active_count() == 1


# ---------------------------------------------------------------------------
# Supersesión
# ---------------------------------------------------------------------------


class TestSupersede:
    def test_superseded_not_surfaced_but_retained(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("old", "la capital es bonn ciudad alemana"))
        idx.supersede("old", _rec("new", "la capital es berlin ciudad alemana"), now_ns=1000)

        # La vieja ya no se surfacea; la nueva sí.
        assert idx.active_count() == 1
        assert idx.count() == 2  # ambas siguen en la tabla (no se borra)
        top = idx.recall_all("la capital es berlin ciudad alemana", k=5)
        ids = [r.lesson_id for r in top]
        assert "new" in ids
        assert "old" not in ids

    def test_include_superseded_shows_old(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("old", "la capital es bonn ciudad alemana"))
        idx.supersede("old", _rec("new", "la capital es berlin ciudad alemana"), now_ns=1000)
        all_ids = [r.lesson_id for r in idx.recall_all(
            "la capital es bonn ciudad alemana", k=5, include_superseded=True)]
        assert "old" in all_ids

    def test_supersede_sets_lineage_and_validity(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("old", "texto viejo aqui"))
        idx.supersede("old", _rec("new", "texto nuevo aqui"), now_ns=4242)
        assert idx.valid_until("old") == 4242
        assert idx.valid_until("new") is None
        assert idx.supersedes_of("new") == "old"


# ---------------------------------------------------------------------------
# Olvido (retire) sin reemplazo
# ---------------------------------------------------------------------------


class TestRetire:
    def test_retire_hides_but_keeps(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "dato obsoleto cualquiera"))
        idx.retire("r1", now_ns=99)
        assert idx.active_count() == 0
        assert idx.count() == 1
        assert idx.recall("dato obsoleto cualquiera") is None
        assert idx.valid_until("r1") == 99


# ---------------------------------------------------------------------------
# Auditoría en cadena Merkle
# ---------------------------------------------------------------------------


class TestMerkleAudit:
    def test_transitions_anchored_and_chain_verifies(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        idx = _idx(tmp_path, merkle=merkle)
        idx.upsert(_rec("old", "texto viejo aqui"))
        idx.supersede("old", _rec("new", "texto nuevo aqui"), now_ns=1)
        idx.retire("new", now_ns=2)
        ok, msg = merkle.verify_chain()
        assert ok, msg
        # Al menos dos eventos de transición registrados.
        actions = [r.action for r in merkle.tail(10)]
        assert "memory.superseded" in actions
        assert "memory.retired" in actions

    def test_no_merkle_is_fine(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)  # sin merkle
        idx.upsert(_rec("old", "texto viejo aqui"))
        idx.supersede("old", _rec("new", "texto nuevo aqui"), now_ns=1)  # no lanza
        assert idx.active_count() == 1
