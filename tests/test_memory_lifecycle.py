"""
Cierre de las deudas tipo-1 (construir-encima) + test de CICLO DE VIDA completo.

Deudas cerradas:
- pending→retire tras grace: `apply_decay(retire_after_ns=...)`.
- auto-touch en recall: `SqliteMemoryIndex(auto_touch=True)`.
- el inquilino de seguridad expone supersede/retire/tiers.

El test de ciclo de vida prueba las tres JUNTAS de punta a punta (acceso→promoción→
ocio→pending→grace→retire), anclado en cadena — que es lo que demuestra que el
tipo-1 quedó realmente cerrado, no tres piezas sueltas.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.lesson_index import SqliteLessonIndex
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord

_PASS_EV = {"verdict": "pass"}


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t")


def _lesson(lid: str, avoid: str) -> Lesson:
    return Lesson(
        id=lid, title="t", provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic="h", avoid_pattern=avoid, evidence=_PASS_EV,
    )


# ---------------------------------------------------------------------------
# Deuda #1: pending → retire tras grace
# ---------------------------------------------------------------------------


class TestRetireAfterGrace:
    def test_decay_retires_past_grace(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("fresh", "f"), valid_from_ns=100)
        idx.upsert(_rec("ancient", "a"), valid_from_ns=0)
        # pending_after=30, retire_after=50: ancient (idle 100) supera el grace → retirada.
        idx.apply_decay(now_ns=100, warm_after_ns=10, cold_after_ns=20,
                        pending_after_ns=30, retire_after_ns=50)
        assert idx.valid_until("ancient") == 100   # caducada
        assert idx.active_count() == 1             # solo fresh sigue vigente
        assert idx.count() == 2                    # ancient NO se borra
        assert idx.tier("fresh") == "hot"

    def test_pending_within_grace_survives(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
        idx.upsert(_rec("r", "x"), valid_from_ns=0)
        # idle 40: > pending_after(30) pero < retire_after(50) → pending, NO retira.
        idx.apply_decay(now_ns=40, warm_after_ns=10, cold_after_ns=20,
                        pending_after_ns=30, retire_after_ns=50)
        assert idx.tier("r") == "pending"
        assert idx.valid_until("r") is None


# ---------------------------------------------------------------------------
# Deuda #2: auto-touch en recall
# ---------------------------------------------------------------------------


class TestAutoTouch:
    def test_recall_bumps_access_when_enabled(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), auto_touch=True)
        idx.upsert(_rec("r1", "eval user_input arbitrario"), valid_from_ns=0)
        idx.apply_decay(now_ns=1000, warm_after_ns=10, cold_after_ns=20, pending_after_ns=30)
        assert idx.tier("r1") == "pending"
        # Un recall con match lo revive automáticamente.
        res = idx.recall("eval user_input arbitrario")
        assert res is not None and res.matched
        assert idx.tier("r1") == "hot"
        assert idx.access_count("r1") == 1

    def test_default_recall_does_not_touch(self, tmp_path: Path) -> None:
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))  # auto_touch=False
        idx.upsert(_rec("r1", "eval user_input arbitrario"), valid_from_ns=0)
        idx.recall("eval user_input arbitrario")
        assert idx.access_count("r1") == 0


# ---------------------------------------------------------------------------
# Deuda #3: el tenant de seguridad expone el ciclo de vida
# ---------------------------------------------------------------------------


class TestTenantLifecycle:
    def test_lesson_supersede_and_retire(self, tmp_path: Path) -> None:
        store = LessonStore(tmp_path / "lessons")
        store.add(_lesson("l1", "eval user_input arbitrario"))
        idx = SqliteLessonIndex(tmp_path / "idx.db", embedder=StubEmbedder(dim=64), store=store)
        idx.rebuild_from(store)

        # Una heurística refinada reemplaza a la vieja.
        idx.supersede("l1", _lesson("l2", "eval user_input ejecuta arbitrario peligroso"),
                      now_ns=500)
        current = [r.lesson_id for r in idx.recall_all("eval user_input arbitrario", k=5)]
        assert "l2" in current and "l1" not in current

        # Y se puede retirar una lección obsoleta.
        idx.retire("l2", now_ns=600)
        assert idx.active_count() == 0


# ---------------------------------------------------------------------------
# CICLO DE VIDA COMPLETO (las tres juntas, anclado en cadena)
# ---------------------------------------------------------------------------


def test_full_lifecycle_anchored(tmp_path: Path) -> None:
    merkle = MerkleLogger(log_dir=tmp_path / "merkle")
    idx = SqliteMemoryIndex(
        tmp_path / "m.db", embedder=StubEmbedder(dim=64), merkle=merkle, auto_touch=True
    )
    idx.upsert(_rec("r1", "patron de ataque conocido aqui"), valid_from_ns=0)

    # 1. Ocio → democión a pending (dentro del grace).
    idx.apply_decay(now_ns=40, warm_after_ns=10, cold_after_ns=20,
                    pending_after_ns=30, retire_after_ns=100)
    assert idx.tier("r1") == "pending"

    # 2. Se vuelve a necesitar → recall lo revive (auto-touch) a hot, en t=40.
    res = idx.recall("patron de ataque conocido aqui", now_ns=40)
    assert res is not None and res.matched
    assert idx.tier("r1") == "hot"

    # 3. Ocio largo desde el último acceso (t=40) → supera el grace → retiro.
    idx.apply_decay(now_ns=400, warm_after_ns=10, cold_after_ns=20,
                    pending_after_ns=30, retire_after_ns=100)
    assert idx.active_count() == 0
    assert idx.recall("patron de ataque conocido aqui") is None  # ya no surfacea
    assert idx.count() == 1                                       # pero NO se borró

    # 4. Todo el ciclo quedó probado en cadena, íntegra.
    ok, msg = merkle.verify_chain()
    assert ok, msg
    actions = [r.action for r in merkle.tail(20)]
    assert "memory.decay" in actions
    assert "memory.retired" in actions
