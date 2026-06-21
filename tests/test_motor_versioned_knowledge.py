"""
1c-motor — conocimiento VERSIONADO y demostrable en el tiempo, dominio NO-seguridad.

La transferencia cross-family (detección) tiene una frontera dura (ver 1c-seguridad).
El valor genérico del sustrato es OTRO eje, donde sí gana limpio: conocimiento
empírico que CAMBIA con el tiempo, recordado con procedencia verificable —
responder "¿qué es vigente AHORA, y pruébame cuándo dejó de valer lo anterior?".
Eso es lo que el campo (Mem0/Zep/Letta) admite no resolver y aquí se demuestra
end-to-end, sin Garak, sin detección.
"""

from __future__ import annotations

from pathlib import Path

from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _fact(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t", record_type="empirical")


class TestVersionedKnowledge:
    """Dominio: hechos de empresa que cambian (quién dirige la compañía)."""

    def test_recall_reflects_current_truth_after_supersession(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        idx = SqliteMemoryIndex(tmp_path / "k.db", embedder=StubEmbedder(dim=64), merkle=merkle)

        # Verdad t0: la dirige Alice.
        idx.upsert(_fact("ceo-v1", "la empresa acme esta dirigida por alice martin"))
        r0 = idx.recall("quien dirige la empresa acme alice")
        assert r0 is not None and r0.lesson_id == "ceo-v1"

        # t1: cambia. La nueva verdad SUPERSEDE a la vieja (no se borra).
        idx.supersede(
            "ceo-v1",
            _fact("ceo-v2", "la empresa acme esta dirigida por bob nunez"),
            now_ns=1700000000,
            reason="cambio de direccion anunciado",
        )

        # Recall por defecto = SOLO lo vigente → ya no surfacea a Alice.
        current = [r.lesson_id for r in idx.recall_all("quien dirige la empresa acme", k=5)]
        assert "ceo-v2" in current
        assert "ceo-v1" not in current

        # Pero la historia es recuperable y PROBABLE: Alice sigue, marcada caducada.
        history = [r.lesson_id for r in idx.recall_all(
            "empresa acme dirigida", k=5, include_superseded=True)]
        assert "ceo-v1" in history and "ceo-v2" in history
        assert idx.valid_until("ceo-v1") == 1700000000
        assert idx.valid_until("ceo-v2") is None
        assert idx.supersedes_of("ceo-v2") == "ceo-v1"

    def test_history_is_anchored_and_verifiable(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        idx = SqliteMemoryIndex(tmp_path / "k.db", embedder=StubEmbedder(dim=64), merkle=merkle)
        idx.upsert(_fact("v1", "el precio del producto es diez euros"))
        idx.supersede("v1", _fact("v2", "el precio del producto es doce euros"), now_ns=42)
        # La cadena prueba la transición (qué cambió y cuándo), y verifica íntegra.
        ok, msg = merkle.verify_chain()
        assert ok, msg
        events = [(r.action, r.payload) for r in merkle.tail(5)]
        superseded = [p for a, p in events if a == "memory.superseded"]
        assert superseded and superseded[-1]["old"] == "v1"
        assert superseded[-1]["new"] == "v2"
        assert superseded[-1]["at_ns"] == 42
