"""Tests for ADR-030 block memory (Letta/MemGPT-style core memory)."""

from __future__ import annotations

import pytest

from atlas.memory.block_memory import (
    BlockExists,
    BlockLimitExceeded,
    BlockMemory,
    BlockNotFound,
    MemoryBlock,
)


class FakeMerkle:
    """Captures audit calls so tests can assert mutations are logged."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _mem(tmp_path, merkle=None) -> BlockMemory:
    return BlockMemory(tmp_path / "blocks", merkle=merkle)


# --------------------------------------------------------------------------
# MemoryBlock dataclass
# --------------------------------------------------------------------------


def test_block_chars_and_is_full():
    b = MemoryBlock(label="persona", value="hello", limit=5)
    assert b.chars == 5
    assert b.is_full is True
    b2 = MemoryBlock(label="persona", value="hi", limit=10)
    assert b2.is_full is False


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------


def test_create_and_get(tmp_path):
    mem = _mem(tmp_path)
    block = mem.create("persona", "I am Atlas", description="agent identity")
    assert block.label == "persona"
    assert block.value == "I am Atlas"
    assert mem.get("persona") is block
    assert mem.labels() == ["persona"]


def test_create_duplicate_raises(tmp_path):
    mem = _mem(tmp_path)
    mem.create("persona")
    with pytest.raises(BlockExists):
        mem.create("persona")


def test_create_over_limit_raises(tmp_path):
    mem = _mem(tmp_path)
    with pytest.raises(BlockLimitExceeded):
        mem.create("persona", "x" * 11, limit=10)


# --------------------------------------------------------------------------
# set / append / replace
# --------------------------------------------------------------------------


def test_set_overwrites(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "name unknown")
    mem.set("human", "name: Tomás")
    assert mem.get("human").value == "name: Tomás"


def test_set_over_limit_raises(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", limit=10)
    with pytest.raises(BlockLimitExceeded):
        mem.set("human", "x" * 11)


def test_set_missing_raises(tmp_path):
    mem = _mem(tmp_path)
    with pytest.raises(BlockNotFound):
        mem.set("ghost", "x")


def test_append_joins_with_sep(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "line1")
    mem.append("human", "line2")
    assert mem.get("human").value == "line1\nline2"


def test_append_first_value_no_leading_sep(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human")
    mem.append("human", "first")
    assert mem.get("human").value == "first"


def test_append_over_limit_raises(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "12345", limit=8)
    with pytest.raises(BlockLimitExceeded):
        mem.append("human", "6789")


def test_replace_substring(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "name: unknown")
    mem.replace("human", "unknown", "Tomás")
    assert mem.get("human").value == "name: Tomás"


def test_replace_missing_substring_raises(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "abc")
    with pytest.raises(Exception):
        mem.replace("human", "zzz", "y")


def test_replace_over_limit_raises(tmp_path):
    mem = _mem(tmp_path)
    mem.create("human", "ab", limit=4)
    with pytest.raises(BlockLimitExceeded):
        mem.replace("human", "ab", "abcde")


# --------------------------------------------------------------------------
# delete
# --------------------------------------------------------------------------


def test_delete(tmp_path):
    mem = _mem(tmp_path)
    mem.create("tmp")
    mem.delete("tmp")
    assert mem.get("tmp") is None
    assert mem.labels() == []


def test_delete_missing_raises(tmp_path):
    mem = _mem(tmp_path)
    with pytest.raises(BlockNotFound):
        mem.delete("ghost")


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def test_render_is_deterministic_and_labelled(tmp_path):
    mem = _mem(tmp_path)
    mem.create("persona", "P")
    mem.create("human", "H")
    rendered = mem.render()
    # ordered by label: human before persona
    assert rendered == "<human>\nH\n</human>\n<persona>\nP\n</persona>"


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------


def test_persistence_reload(tmp_path):
    mem = _mem(tmp_path)
    mem.create("persona", "I am Atlas", description="identity")
    mem.append("persona", "v2")

    reloaded = _mem(tmp_path)
    block = reloaded.get("persona")
    assert block is not None
    assert block.value == "I am Atlas\nv2"
    assert block.description == "identity"


def test_corrupt_file_loads_empty(tmp_path):
    d = tmp_path / "blocks"
    d.mkdir(parents=True)
    (d / "blocks.json").write_text("{not json", encoding="utf-8")
    mem = BlockMemory(d)
    assert mem.labels() == []


# --------------------------------------------------------------------------
# Merkle audit
# --------------------------------------------------------------------------


def test_mutations_are_audited(tmp_path):
    merkle = FakeMerkle()
    mem = _mem(tmp_path, merkle=merkle)
    mem.create("persona", "a")
    mem.set("persona", "b")
    mem.append("persona", "c")
    mem.replace("persona", "c", "d")
    mem.delete("persona")

    actions = [c["action"] for c in merkle.calls]
    assert actions == [
        "memory.block.created",
        "memory.block.edited",
        "memory.block.edited",
        "memory.block.edited",
        "memory.block.deleted",
    ]
    assert all(c["agent"] == "block_memory" for c in merkle.calls)


def test_no_merkle_is_safe(tmp_path):
    mem = _mem(tmp_path, merkle=None)
    mem.create("persona", "a")  # must not raise
    assert mem.get("persona").value == "a"
