from __future__ import annotations

from pathlib import Path

from atlas.memory.memory_index import SqliteMemoryIndex, PERSONAL_TTL_S
from atlas.memory.record import GenericRecord


def _cols(idx: SqliteMemoryIndex) -> set[str]:
    return {r[1] for r in idx._conn.execute("PRAGMA table_info(records)")}


def test_migration_adds_class_and_ttl_columns(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    cols = _cols(idx)
    assert "memory_class" in cols
    assert "expires_at" in cols


def test_personal_ttl_constant_is_90_days() -> None:
    assert PERSONAL_TTL_S == 90 * 24 * 3600


def test_preexisting_row_defaults_to_factual(tmp_path: Path) -> None:
    # Fila escrita con el esquema base, sin memory_class explícito → factual.
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="r1", text="el agua hierve a 100C"))
    row = idx._conn.execute(
        "SELECT memory_class, expires_at FROM records WHERE id='r1'"
    ).fetchone()
    assert row[0] == "factual"
    assert row[1] is None
