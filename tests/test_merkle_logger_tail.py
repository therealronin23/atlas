"""Regression tests for bounded Merkle audit-log tail reads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, IO, Iterator

import pytest

from atlas.logging.merkle_logger import AuditRecord, MerkleLogger


def _jsonl_record(action: str, *, payload: dict[str, Any] | None = None) -> str:
    record = AuditRecord(
        action=action,
        agent="tail-test",
        result="success",
        risk_level="safe",
        payload=payload or {},
    )
    return json.dumps(record.to_dict(), ensure_ascii=False) + "\n"


def _write_records(path: Path, actions: list[str]) -> None:
    path.write_text("".join(_jsonl_record(action) for action in actions), encoding="utf-8")


class _CountingReader:
    """Transparent file wrapper that records bytes consumed by ``tail``."""

    def __init__(self, raw: IO[Any], counter: dict[str, int]) -> None:
        self._raw = raw
        self._counter = counter

    def __enter__(self) -> _CountingReader:
        self._raw.__enter__()
        return self

    def __exit__(self, *args: object) -> object:
        return self._raw.__exit__(*args)

    def __iter__(self) -> Iterator[Any]:
        for value in self._raw:
            self._count(value)
            yield value

    def read(self, size: int = -1) -> Any:
        value = self._raw.read(size)
        self._count(value)
        return value

    def _count(self, value: Any) -> None:
        if isinstance(value, str):
            self._counter["bytes"] += len(value.encode("utf-8"))
        else:
            self._counter["bytes"] += len(value)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def test_tail_preserves_order_across_rotated_files(tmp_path: Path) -> None:
    _write_records(
        tmp_path / "merkle-20260715_120000.jsonl",
        ["event.0", "event.1"],
    )
    _write_records(
        tmp_path / "merkle-20260715_130000.jsonl",
        ["event.2", "event.3"],
    )
    _write_records(tmp_path / "merkle.jsonl", ["event.4", "event.5"])

    logger = MerkleLogger(tmp_path)

    assert [record.action for record in logger.tail(4)] == [
        "event.2",
        "event.3",
        "event.4",
        "event.5",
    ]
    assert [record.action for record in logger.tail(20)] == [
        f"event.{index}" for index in range(6)
    ]


def test_tail_decodes_utf8_record_larger_than_a_read_block(tmp_path: Path) -> None:
    expected_text = "ámbito-🧭-" * 10_000
    log_file = tmp_path / "merkle.jsonl"
    log_file.write_text(
        _jsonl_record("event.before")
        + _jsonl_record("event.utf8", payload={"text": expected_text}),
        encoding="utf-8",
    )
    logger = MerkleLogger(tmp_path)

    records = logger.tail(1)

    assert len(records) == 1
    assert records[0].action == "event.utf8"
    assert records[0].payload["text"] == expected_text


def test_tail_preserves_historical_non_positive_n_semantics(tmp_path: Path) -> None:
    _write_records(
        tmp_path / "merkle.jsonl",
        ["event.0", "event.1", "event.2", "event.3"],
    )
    logger = MerkleLogger(tmp_path)

    assert [record.action for record in logger.tail(0)] == [
        "event.0",
        "event.1",
        "event.2",
        "event.3",
    ]
    assert [record.action for record in logger.tail(-2)] == [
        "event.2",
        "event.3",
    ]


def test_tail_reads_a_bounded_fraction_of_a_large_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_file = tmp_path / "merkle.jsonl"
    rows = [
        _jsonl_record(
            "event.large",
            payload={"index": index, "padding": "x" * 2_048},
        )
        for index in range(1_500)
    ]
    log_file.write_text("".join(rows), encoding="utf-8")
    logger = MerkleLogger(tmp_path)

    counter = {"bytes": 0}
    original_open = Path.open

    def counted_open(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        raw = original_open(path, *args, **kwargs)
        if path == log_file:
            return _CountingReader(raw, counter)  # type: ignore[return-value]
        return raw

    monkeypatch.setattr(Path, "open", counted_open)

    records = logger.tail(3)

    assert [record.payload["index"] for record in records] == [1497, 1498, 1499]
    assert counter["bytes"] <= 128 * 1_024
