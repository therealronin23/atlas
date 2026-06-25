from __future__ import annotations

import time
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


def test_upsert_personal_derives_ttl(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    before = time.time()
    idx.upsert(GenericRecord(record_id="p1", text="me gusta el café"), memory_class="personal")
    row = idx._conn.execute(
        "SELECT memory_class, expires_at FROM records WHERE id='p1'"
    ).fetchone()
    assert row[0] == "personal"
    assert row[1] is not None
    # expires_at ≈ now + PERSONAL_TTL_S
    assert before + PERSONAL_TTL_S <= row[1] <= time.time() + PERSONAL_TTL_S + 5


def test_upsert_factual_has_no_expiry(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="f1", text="París es la capital de Francia"),
               memory_class="factual")
    row = idx._conn.execute("SELECT expires_at FROM records WHERE id='f1'").fetchone()
    assert row[0] is None


def test_upsert_explicit_expires_at_wins(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="p2", text="x"), memory_class="personal",
               expires_at=123.0)
    row = idx._conn.execute("SELECT expires_at FROM records WHERE id='p2'").fetchone()
    assert row[0] == 123.0
