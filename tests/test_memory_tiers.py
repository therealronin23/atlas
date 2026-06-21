"""
Tests de niveles de memoria + democión medible (Fase 1d-b, sobre el motor).

Capa B del diseño: ataca consolidación/"cajón de sastre" y "¿quién audita el olvido?".
- tiers hot/warm/cold/pending con `last_access_ns` + `access_count`.
- democión por señales MEDIBLES (tiempo ocioso desde el último acceso) → no juicio
  arbitrario, reproducible.
- RECUPERABLE: tocar (acceder) una memoria la promociona de vuelta a hot.
- `pending` = suelo/grace antes de retirar del índice; el retiro sigue siendo una
  decisión SEPARADA y auditable (no se borra automáticamente; la cadena nunca borra).
"""

from __future__ import annotations

from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _idx(tmp_path: Path) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64))


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t")


# Umbrales de ocio (ns) ascendentes: warm < cold < pending.
THR = dict(warm_after_ns=10, cold_after_ns=20, pending_after_ns=30)


class TestTiers:
    def test_new_record_is_hot(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "algo"), valid_from_ns=0)
        assert idx.tier("r1") == "hot"

    def test_decay_demotes_by_idle_time(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("hot", "h"), valid_from_ns=100)    # recién
        idx.upsert(_rec("warm", "w"), valid_from_ns=85)    # idle 15
        idx.upsert(_rec("cold", "c"), valid_from_ns=75)    # idle 25
        idx.upsert(_rec("pend", "p"), valid_from_ns=50)    # idle 50
        idx.apply_decay(now_ns=100, **THR)
        assert idx.tier("hot") == "hot"
        assert idx.tier("warm") == "warm"
        assert idx.tier("cold") == "cold"
        assert idx.tier("pend") == "pending"

    def test_touch_promotes_back_to_hot(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "algo"), valid_from_ns=0)
        idx.apply_decay(now_ns=100, **THR)
        assert idx.tier("r1") == "pending"
        idx.touch("r1", now_ns=100)
        assert idx.tier("r1") == "hot"
        assert idx.access_count("r1") == 1
        # Tras tocar, el ocio se mide desde el toque: sigue hot un rato.
        idx.apply_decay(now_ns=105, **THR)
        assert idx.tier("r1") == "hot"

    def test_pending_does_not_auto_retire(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "algo"), valid_from_ns=0)
        idx.apply_decay(now_ns=1000, **THR)
        assert idx.tier("r1") == "pending"
        # pending = grace: sigue VIGENTE y recuperable; no se ha caducado.
        assert idx.valid_until("r1") is None
        assert idx.active_count() == 1

    def test_tier_counts(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("a", "x"), valid_from_ns=100)
        idx.upsert(_rec("b", "y"), valid_from_ns=50)
        idx.apply_decay(now_ns=100, **THR)
        counts = idx.tier_counts()
        assert counts.get("hot") == 1
        assert counts.get("pending") == 1

    def test_decay_only_touches_active(self, tmp_path: Path) -> None:
        idx = _idx(tmp_path)
        idx.upsert(_rec("r1", "algo"), valid_from_ns=0)
        idx.retire("r1", now_ns=5)  # ya caducada
        idx.apply_decay(now_ns=1000, **THR)
        # No se reclasifica una memoria ya retirada (no vigente).
        assert idx.tier("r1") == "hot"  # sin cambios


class TestDecayAudit:
    def test_decay_anchored_in_merkle(self, tmp_path: Path) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        idx = SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), merkle=merkle)
        idx.upsert(_rec("r1", "algo"), valid_from_ns=0)
        idx.apply_decay(now_ns=1000, **THR)
        ok, msg = merkle.verify_chain()
        assert ok, msg
        assert "memory.decay" in [r.action for r in merkle.tail(5)]
