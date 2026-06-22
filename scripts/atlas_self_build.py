#!/usr/bin/env python3
"""Atlas self-build dry-run report.

Loads docs/backlog.yaml and prints pending items ordered by priority.
Does NOT generate code, does NOT touch git.

Usage:
    python scripts/atlas_self_build.py
    python scripts/atlas_self_build.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from atlas.core.self_maintenance.backlog import BacklogItem, load_backlog, pending

_DEFAULT_BACKLOG = _REPO_ROOT / "docs" / "backlog.yaml"


def _item_to_dict(item: BacklogItem) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "priority": item.priority,
        "targets": list(item.targets),
        "acceptance": item.acceptance,
        "why": item.why,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Atlas self-build dry-run: list pending backlog items."
    )
    parser.add_argument(
        "--backlog",
        type=Path,
        default=_DEFAULT_BACKLOG,
        help="Path to backlog YAML (default: docs/backlog.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    items = load_backlog(args.backlog)
    queue = pending(items)

    if args.as_json:
        output = {
            "pending_count": len(queue),
            "items": [_item_to_dict(i) for i in queue],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print(f"Atlas self-build — dry-run report")
    print(f"Backlog: {args.backlog}")
    print(f"{'=' * 60}")

    if not queue:
        print("No pending items.")
        return

    for idx, item in enumerate(queue, start=1):
        print(f"\n[{idx}] {item.id}  (priority {item.priority})")
        print(f"    Title      : {item.title}")
        print(f"    Targets    : {', '.join(item.targets) if item.targets else '(none)'}")
        print(f"    Acceptance : {item.acceptance[:120]}{'...' if len(item.acceptance) > 120 else ''}")

    print(f"\n{'=' * 60}")
    print(
        f"{len(queue)} items pendientes; el motor de auto-construccion los atacaria en este orden."
    )


if __name__ == "__main__":
    main()
