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
        items.append(
            BacklogItem(
                id=entry["id"],
                title=entry["title"],
                why=str(entry["why"]).strip(),
                targets=tuple(entry.get("targets", [])),
                acceptance=str(entry["acceptance"]).strip(),
                priority=int(entry["priority"]),
                status=status,
            )
        )
    return items


def pending(items: list[BacklogItem]) -> list[BacklogItem]:
    """Return items with status 'pending', sorted by priority ascending."""
    return sorted(
        (item for item in items if item.status == "pending"),
        key=lambda i: i.priority,
    )
