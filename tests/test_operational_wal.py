"""
Tests for OperationalWAL (ADR-024).

Coverage:
  (a) write → tail roundtrip — entries returned in order
  (b) crash recovery — partial/truncated record at EOF is silently skipped
  (c) rotation — when MAX_BYTES is exceeded the active file is renamed and a
      fresh file is started
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.logging.operational_wal import OperationalWAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wal(tmp_path: Path) -> OperationalWAL:
    return OperationalWAL(tmp_path / "wal")


# ---------------------------------------------------------------------------
# (a) write → tail roundtrip
# ---------------------------------------------------------------------------

class TestWriteTailRoundtrip:
    def test_single_entry_recovered(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("comp", "hello", user="alice")
        entries = wal.tail()
        assert len(entries) == 1
        e = entries[0]
        assert e["component"] == "comp"
        assert e["message"] == "hello"
        assert e["fields"]["user"] == "alice"
        assert "ts" in e

    def test_order_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        messages = [f"msg-{i}" for i in range(10)]
        for m in messages:
            wal.write("c", m)
        recovered = [e["message"] for e in wal.tail(n=20)]
        assert recovered == messages

    def test_tail_n_limits_result(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        for i in range(10):
            wal.write("c", f"m{i}")
        assert len(wal.tail(n=3)) == 3

    def test_tail_returns_last_n(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        for i in range(5):
            wal.write("c", f"m{i}")
        last = wal.tail(n=2)
        assert [e["message"] for e in last] == ["m3", "m4"]

    def test_empty_log_returns_empty_list(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        assert wal.tail() == []

    def test_redaction_of_secret_fields(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("auth", "login", api_key="s3cr3t", user="bob")
        entry = wal.tail()[0]
        assert entry["fields"]["api_key"] == "[REDACTED]"
        assert entry["fields"]["user"] == "bob"

    def test_redaction_of_nested_key_name(self, tmp_path: Path) -> None:
        """Keys whose *name* contains a redact word should be redacted."""
        wal = _wal(tmp_path)
        wal.write("svc", "op", x_api_key="hidden", bearer_token="also-hidden")
        entry = wal.tail()[0]
        assert entry["fields"]["x_api_key"] == "[REDACTED]"
        assert entry["fields"]["bearer_token"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# (b) crash recovery — partial record at EOF
# ---------------------------------------------------------------------------

class TestCrashRecovery:
    def _write_and_corrupt(self, tmp_path: Path) -> tuple[OperationalWAL, Path]:
        """Write two good entries, then append half a JSON line (simulates crash)."""
        wal = _wal(tmp_path)
        wal.write("c", "good-1")
        wal.write("c", "good-2")
        log_file = tmp_path / "wal" / "operational.jsonl"
        # Append a truncated JSON object (simulates a mid-write crash)
        with log_file.open("ab") as f:
            f.write(b'{"ts":"2026-01-01","component":"c","message":"bad"')
        return wal, log_file

    def test_partial_record_skipped(self, tmp_path: Path) -> None:
        wal, _ = self._write_and_corrupt(tmp_path)
        entries = wal.tail(n=10)
        messages = [e["message"] for e in entries]
        assert "good-1" in messages
        assert "good-2" in messages
        # The corrupt record must not appear
        assert "bad" not in messages

    def test_partial_record_does_not_raise(self, tmp_path: Path) -> None:
        wal, _ = self._write_and_corrupt(tmp_path)
        # Must not raise any exception
        entries = wal.tail(n=10)
        assert isinstance(entries, list)

    def test_good_entries_intact_after_corruption(self, tmp_path: Path) -> None:
        wal, _ = self._write_and_corrupt(tmp_path)
        entries = wal.tail(n=10)
        # Exactly the two good entries survive
        assert len(entries) == 2

    def test_entirely_empty_lines_skipped(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "ok")
        log_file = tmp_path / "wal" / "operational.jsonl"
        with log_file.open("ab") as f:
            f.write(b"\n\n")
        entries = wal.tail(n=10)
        assert len(entries) == 1

    def test_garbage_line_skipped(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "real")
        log_file = tmp_path / "wal" / "operational.jsonl"
        with log_file.open("ab") as f:
            f.write(b"NOT JSON AT ALL\n")
        entries = wal.tail(n=10)
        assert len(entries) == 1
        assert entries[0]["message"] == "real"


# ---------------------------------------------------------------------------
# (c) rotation semantics
# ---------------------------------------------------------------------------

class TestRotation:
    def _tiny_wal(self, tmp_path: Path, max_bytes: int = 200) -> OperationalWAL:
        """Return a WAL with a tiny rotation threshold for testing."""
        wal = OperationalWAL(tmp_path / "wal")
        wal.MAX_BYTES = max_bytes  # override class attribute on instance
        return wal

    def test_rotation_creates_archive_file(self, tmp_path: Path) -> None:
        wal = self._tiny_wal(tmp_path, max_bytes=200)
        # Write enough data to trigger a rotation
        for i in range(20):
            wal.write("c", f"entry-{i:04d}-padding-to-fill-space")
        wal_dir = tmp_path / "wal"
        archive_files = [
            f for f in wal_dir.iterdir()
            if f.name.startswith("operational.") and f.name != "operational.jsonl"
        ]
        assert len(archive_files) >= 1, "Expected at least one rotated archive file"

    def test_active_file_continues_after_rotation(self, tmp_path: Path) -> None:
        wal = self._tiny_wal(tmp_path, max_bytes=200)
        for i in range(20):
            wal.write("c", f"entry-{i:04d}-padding-to-fill-space")
        # After rotation the active file still exists and is readable
        active = tmp_path / "wal" / "operational.jsonl"
        assert active.exists()
        entries = wal.tail(n=100)
        assert len(entries) >= 1

    def test_rotated_file_contains_valid_jsonl(self, tmp_path: Path) -> None:
        wal = self._tiny_wal(tmp_path, max_bytes=200)
        for i in range(20):
            wal.write("c", f"entry-{i:04d}-padding-to-fill-space")
        wal_dir = tmp_path / "wal"
        archive_files = [
            f for f in wal_dir.iterdir()
            if f.name.startswith("operational.") and f.name != "operational.jsonl"
        ]
        for arc in archive_files:
            for line in arc.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    obj = json.loads(line)  # must not raise
                    assert "component" in obj
