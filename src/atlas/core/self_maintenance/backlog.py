"""Backlog loader for Atlas self-maintenance.

Parses docs/backlog.yaml and exposes BacklogItem dataclass + helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

VALID_STATUSES = {"pending", "doing", "done"}


@dataclass(frozen=True)
class BacklogItem:
    id: str
    title: str
    why: str
    targets: tuple[str, ...]
    acceptance: str
    priority: int
    status: str
    test_cmd: tuple[str, ...] | None = None


def load_backlog(path: Path) -> list[BacklogItem]:
    """Parse a backlog YAML file and return a list of BacklogItem.

    Raises ValueError if any item has an unknown status.
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    items: list[BacklogItem] = []
    for entry in raw.get("items", []):
        status: str = entry["status"]
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Item '{entry['id']}' has invalid status '{status}'. "
                f"Allowed: {sorted(VALID_STATUSES)}"
            )
        # test_cmd es opcional (backward-compat): items existentes sin el
        # campo siguen cargando igual, con test_cmd=None.
        raw_test_cmd = entry.get("test_cmd")
        items.append(
            BacklogItem(
                id=entry["id"],
                title=entry["title"],
                why=str(entry["why"]).strip(),
                targets=tuple(entry.get("targets", [])),
                acceptance=str(entry["acceptance"]).strip(),
                priority=int(entry["priority"]),
                status=status,
                test_cmd=tuple(raw_test_cmd) if raw_test_cmd else None,
            )
        )
    return items


def pending(items: list[BacklogItem]) -> list[BacklogItem]:
    """Return items with status 'pending', sorted by priority ascending."""
    return sorted(
        (item for item in items if item.status == "pending"),
        key=lambda i: i.priority,
    )


def backlog_summary(items: list[BacklogItem]) -> dict[str, Any]:
    """Índice ligero del backlog: conteo por status + los 5 pendientes de mayor
    prioridad (id/title/priority, sin why/acceptance — eso es el detalle)."""
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    top_pending = [
        {"id": item.id, "title": item.title, "priority": item.priority}
        for item in pending(items)[:5]
    ]
    return {"total": len(items), "by_status": by_status, "top_pending": top_pending}
