"""Resolve repository data in both source checkouts and installed wheels."""

from __future__ import annotations

import os
import sysconfig
from pathlib import Path


def atlas_data_root() -> Path:
    """Return the root containing ``config/`` and packaged ``fixtures/``."""
    candidates: list[Path] = []
    configured = os.environ.get("ATLAS_CORE_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path(__file__).resolve().parents[2],
            Path.cwd(),
            Path(sysconfig.get_path("data")) / "share" / "atlas-core",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "config").is_dir() or (resolved / "fixtures").is_dir():
            return resolved
    return candidates[-1].resolve()
