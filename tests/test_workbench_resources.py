"""Tests del builder de Resources de la mesa de trabajo (puro, sin MCP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.lesson_store import (
    Lesson,
    LessonProvenance,
    LessonStore,
    LessonVerifier,
    ProveItResult,
)
from atlas.core.self_maintenance.backlog import BacklogItem
from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.workbench_resources import workbench_hash, workbench_manifest_json


def _entry(
    name: str,
    *,
    kind: str = "mcp",
    sector: str = "programacion",
    subsector: str = "frontend",
    status: str = "verificado",
    mode: str = "connected",
) -> CatalogEntry:
    return CatalogEntry(
        name=name,
        sector=sector,
        sector_label=sector.title(),
        kind=kind,
        purpose=f"purpose of {name}",
        source=f"src/{name}",
        install=f"npx {name}",
        status=status,
        tags=["a", "b"],
        mode=mode,
        subsector=subsector,
    )


def _backlog_item(id: str, priority: int, status: str = "pending") -> BacklogItem:
    return BacklogItem(
        id=id,
        title=f"Title {id}",
        why="why",
        targets=(),
        acceptance="acc",
        priority=priority,
        status=status,
    )


def _prove_it() -> Lesson:
    result = ProveItResult(
        test_path="tests/test_x.py::test_y",
        fix_commit="abc1234",
        failed_before=True,
        passes_after=True,
    )
    ev = LessonVerifier().verify_internal(result).to_dict()
    return Lesson(
        id="lesson-1",
        title="Lesson 1",
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic="h",
        avoid_pattern="p",
        evidence=ev,
    )


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


def test_workbench_manifest_has_four_summary_keys(store: LessonStore) -> None:
    store.add(_prove_it())
    catalog_entries = [_entry("foo", kind="mcp"), _entry("bar", kind="skill")]
    backlog_items = [_backlog_item("a", 1), _backlog_item("b", 2, status="done")]

    data = json.loads(
        workbench_manifest_json(catalog_entries, store, backlog_items, memory_count=42)
    )

    summary = data["summary"]
    assert set(summary.keys()) == {"catalog", "lessons", "backlog", "memory"}
    assert summary["catalog"] == {
        "total": 2,
        "by_status": {"verificado": 2},
        "by_kind": {"mcp": 1, "skill": 1},
    }
    assert summary["lessons"] == {"total": 1, "by_provenance": {"internal_failure": 1}}
    assert summary["backlog"] == {"total": 2, "by_status": {"pending": 1, "done": 1}}
    assert summary["memory"] == {"count": 42}


def test_workbench_manifest_fresh_is_16_char_hash(store: LessonStore) -> None:
    data = json.loads(workbench_manifest_json([], store, [], memory_count=0))
    assert isinstance(data["fresh"], str)
    assert len(data["fresh"]) == 16


def test_workbench_manifest_backlog_top_pending_promoted_to_root(store: LessonStore) -> None:
    backlog_items = [_backlog_item("a", 2), _backlog_item("b", 1)]
    data = json.loads(workbench_manifest_json([], store, backlog_items, memory_count=0))
    assert "top_pending" not in data["summary"]["backlog"]
    assert [t["id"] for t in data["backlog_top_pending"]] == ["b", "a"]


def test_workbench_hash_changes_on_memory_count(store: LessonStore) -> None:
    lesson_stats = store.stats()
    h1 = workbench_hash([], lesson_stats, [], memory_count=0)
    h2 = workbench_hash([], lesson_stats, [], memory_count=1)
    assert h1 != h2


def test_workbench_hash_changes_on_lesson_total(store: LessonStore) -> None:
    stats_empty = store.stats()
    store.add(_prove_it())
    stats_one = store.stats()
    h1 = workbench_hash([], stats_empty, [], memory_count=0)
    h2 = workbench_hash([], stats_one, [], memory_count=0)
    assert h1 != h2


def test_workbench_hash_stable_for_same_inputs(store: LessonStore) -> None:
    lesson_stats = store.stats()
    backlog_items = [_backlog_item("a", 1)]
    catalog_entries = [_entry("foo")]
    h1 = workbench_hash(catalog_entries, lesson_stats, backlog_items, memory_count=5)
    h2 = workbench_hash(catalog_entries, lesson_stats, backlog_items, memory_count=5)
    assert h1 == h2
