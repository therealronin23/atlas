"""Tests for src/atlas/core/self_maintenance/backlog.py."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atlas.core.self_maintenance.backlog import (
    BacklogItem,
    backlog_summary,
    load_backlog,
    pending,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "backlog.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Core tests
# ---------------------------------------------------------------------------

def test_load_and_pending_order(tmp_path: Path) -> None:
    """load_backlog + pending: 2 pending sorted by priority; done excluded."""
    yaml_path = _write_yaml(
        tmp_path,
        """\
        items:
          - id: item-a
            title: "Item A"
            why: "reason A"
            targets: ["src/foo.py"]
            acceptance: "acc A"
            priority: 2
            status: pending
          - id: item-b
            title: "Item B"
            why: "reason B"
            targets: ["src/bar.py"]
            acceptance: "acc B"
            priority: 1
            status: pending
          - id: item-c
            title: "Item C"
            why: "reason C"
            targets: []
            acceptance: "acc C"
            priority: 1
            status: done
        """,
    )

    items = load_backlog(yaml_path)
    assert len(items) == 3

    queue = pending(items)
    assert len(queue) == 2  # done excluded
    assert queue[0].id == "item-b"  # priority 1 first
    assert queue[1].id == "item-a"  # priority 2 second


def test_pending_excludes_done(tmp_path: Path) -> None:
    """pending() must not return done items."""
    yaml_path = _write_yaml(
        tmp_path,
        """\
        items:
          - id: done-item
            title: "Done"
            why: "was done"
            targets: []
            acceptance: "already done"
            priority: 1
            status: done
        """,
    )
    items = load_backlog(yaml_path)
    assert pending(items) == []


def test_invalid_status_raises(tmp_path: Path) -> None:
    """load_backlog must raise ValueError for unknown status values."""
    yaml_path = _write_yaml(
        tmp_path,
        """\
        items:
          - id: bad-item
            title: "Bad"
            why: "bad"
            targets: []
            acceptance: "none"
            priority: 1
            status: wip
        """,
    )
    with pytest.raises(ValueError, match="invalid status"):
        load_backlog(yaml_path)


def test_backlog_item_is_frozen(tmp_path: Path) -> None:
    """BacklogItem must be immutable (frozen dataclass)."""
    item = BacklogItem(
        id="x",
        title="X",
        why="y",
        targets=("a",),
        acceptance="z",
        priority=1,
        status="pending",
    )
    with pytest.raises((AttributeError, TypeError)):
        item.priority = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: real docs/backlog.yaml
# ---------------------------------------------------------------------------

def test_real_backlog_has_enough_pending_items() -> None:
    """Suelo de 'runway': el motor de auto-construcción no debe quedarse sin trabajo.

    Es un piso, no un tamaño fijo del seed: a medida que se completan items (status
    done) la cola baja, y cuando cruza este umbral toca REPONER el backlog con trabajo
    real (Fase 2/3). No se rellena con items ficticios para pasar el test.
    """
    repo_root = Path(__file__).resolve().parent.parent
    backlog_path = repo_root / "docs" / "backlog.yaml"
    if not backlog_path.exists():
        pytest.skip("docs/backlog.yaml not found")

    items = load_backlog(backlog_path)
    queue = pending(items)
    assert len(queue) >= 3, f"Backlog runway agotado: {len(queue)} pendientes (<3). Reponer."


# ---------------------------------------------------------------------------
# backlog_summary
# ---------------------------------------------------------------------------

def _item(id: str, priority: int, status: str = "pending") -> BacklogItem:
    return BacklogItem(
        id=id,
        title=f"Title {id}",
        why="why",
        targets=(),
        acceptance="acc",
        priority=priority,
        status=status,
    )


def test_backlog_summary_counts_by_status() -> None:
    items = [
        _item("a", 1, "pending"),
        _item("b", 2, "pending"),
        _item("c", 3, "doing"),
        _item("d", 4, "done"),
    ]
    summary = backlog_summary(items)
    assert summary["total"] == 4
    assert summary["by_status"] == {"pending": 2, "doing": 1, "done": 1}


def test_backlog_summary_top_pending_capped_at_five_and_ordered() -> None:
    items = [_item(f"p{i}", priority=i, status="pending") for i in range(7, 0, -1)]
    summary = backlog_summary(items)
    top = summary["top_pending"]
    assert len(top) == 5
    assert [t["priority"] for t in top] == [1, 2, 3, 4, 5]
    assert [t["id"] for t in top] == ["p1", "p2", "p3", "p4", "p5"]
    for t in top:
        assert set(t.keys()) == {"id", "title", "priority"}


def test_backlog_summary_top_pending_excludes_non_pending() -> None:
    items = [
        _item("done-item", 1, "done"),
        _item("pending-item", 2, "pending"),
    ]
    summary = backlog_summary(items)
    assert [t["id"] for t in summary["top_pending"]] == ["pending-item"]


# ---------------------------------------------------------------------------
# Cola con backoff (2026-07-09): un item que falla N ticks cede el turno.
# ---------------------------------------------------------------------------

def test_next_runnable_skips_exhausted_item() -> None:
    from atlas.core.self_maintenance.backlog import (
        MAX_CONSECUTIVE_FAILURES,
        next_runnable,
    )

    items = [_item("a", 1), _item("b", 2)]
    state = {"a": MAX_CONSECUTIVE_FAILURES}
    chosen = next_runnable(items, state)
    assert chosen is not None and chosen.id == "b"


def test_next_runnable_all_exhausted_degrades_to_least_failed() -> None:
    from atlas.core.self_maintenance.backlog import next_runnable

    items = [_item("a", 1), _item("b", 2)]
    state = {"a": 5, "b": 3}
    chosen = next_runnable(items, state)
    assert chosen is not None and chosen.id == "b"


def test_next_runnable_empty_queue_returns_none() -> None:
    from atlas.core.self_maintenance.backlog import next_runnable

    assert next_runnable([_item("a", 1, status="done")], {}) is None


def test_record_outcome_resets_on_success_and_accumulates_on_failure() -> None:
    from atlas.core.self_maintenance.backlog import record_outcome

    state: dict[str, int] = {}
    state = record_outcome(state, "a", success=False)
    state = record_outcome(state, "a", success=False)
    assert state == {"a": 2}
    state = record_outcome(state, "a", success=True)
    assert state == {}


def test_queue_state_roundtrip_and_corrupt_file_fail_open(tmp_path: Path) -> None:
    from atlas.core.self_maintenance.backlog import load_queue_state, save_queue_state

    p = tmp_path / "sub" / "queue_state.json"
    save_queue_state(p, {"a": 2})
    assert load_queue_state(p) == {"a": 2}

    p.write_text("{corrupto", encoding="utf-8")
    assert load_queue_state(p) == {}
    assert load_queue_state(tmp_path / "no-existe.json") == {}
