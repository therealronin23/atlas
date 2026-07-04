"""Regresión: _temporal_decay y _hybrid_temporal devuelven resultados válidos.

No mide R@5 exacto (eso es el benchmark completo), solo que:
- los modos existen en RETRIEVERS
- devuelven RecallResult con lesson_id que existe en el índice
- el modo decay favorece records recientes sobre idénticos en similitud
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _idx(tmp_path: Path) -> SqliteMemoryIndex:
    return SqliteMemoryIndex(tmp_path / "m.db", embedder=StubEmbedder(dim=64), threshold=0.0)


def _rec(rid: str, text: str) -> GenericRecord:
    return GenericRecord(record_id=rid, text=text, created_at="t", record_type="empirical")


def test_retrievers_dict_has_new_modes() -> None:
    import importlib, sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    mod = importlib.import_module("eval_longmemeval")
    assert "temporal_decay" in mod.RETRIEVERS
    assert "hybrid_temporal" in mod.RETRIEVERS


def test_temporal_decay_returns_valid_ids(tmp_path: Path) -> None:
    import importlib, sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    mod = importlib.import_module("eval_longmemeval")

    idx = _idx(tmp_path)
    idx.upsert(_rec("r1", "python asyncio event loop"))
    idx.upsert(_rec("r2", "python asyncio event loop"))

    from eval_longmemeval import SampleCtx
    results = mod.RETRIEVERS["temporal_decay"](idx, "asyncio event loop", 5, SampleCtx())
    ids = {r.lesson_id for r in results}
    assert ids <= {"r1", "r2"}
    assert len(results) >= 1


def test_hybrid_temporal_returns_valid_ids(tmp_path: Path) -> None:
    import importlib, sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    mod = importlib.import_module("eval_longmemeval")

    idx = _idx(tmp_path)
    idx.upsert(_rec("a1", "database indexing strategy"))
    idx.upsert(_rec("a2", "database query optimization"))

    from eval_longmemeval import SampleCtx
    results = mod.RETRIEVERS["hybrid_temporal"](idx, "database indexing", 5, SampleCtx())
    ids = {r.lesson_id for r in results}
    assert ids <= {"a1", "a2"}
    assert len(results) >= 1


def test_decay_prefers_recent_over_old(tmp_path: Path) -> None:
    """Con decay activo, el record más reciente sube en ranking vs el antiguo."""
    idx = _idx(tmp_path)

    # Record "viejo": válido desde hace 200 días
    old_ns = time.time_ns() - int(200 * 86_400 * 1e9)
    idx.upsert(_rec("old", "machine learning gradient descent"))
    # Parchear valid_from_ns manualmente para simular antigüedad
    idx._conn.execute("UPDATE records SET valid_from_ns=? WHERE id='old'", (old_ns,))
    idx._conn.commit()

    # Record "reciente": válido desde hace 5 días
    recent_ns = time.time_ns() - int(5 * 86_400 * 1e9)
    idx.upsert(_rec("recent", "machine learning gradient descent"))
    idx._conn.execute("UPDATE records SET valid_from_ns=? WHERE id='recent'", (recent_ns,))
    idx._conn.commit()

    import importlib, sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    mod = importlib.import_module("eval_longmemeval")
    from eval_longmemeval import SampleCtx

    results = mod.RETRIEVERS["temporal_decay"](idx, "machine learning gradient descent", 5, SampleCtx())
    ids_in_order = [r.lesson_id for r in results]
    # El reciente debe aparecer antes que el viejo
    assert ids_in_order.index("recent") < ids_in_order.index("old")
