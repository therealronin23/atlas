"""Tests for src/atlas/core/self_maintenance/backlog.py."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atlas.core.self_maintenance.backlog import BacklogItem, load_backlog, pending

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
