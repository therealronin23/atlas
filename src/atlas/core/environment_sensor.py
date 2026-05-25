"""
Gate H6 — Environment fingerprint and stale detection for generated artifacts.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvironmentFingerprint:
    python_version: str
    atlas_version: str
    dependency_hash: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> EnvironmentFingerprint:
        return cls(
            python_version=str(data.get("python_version", "")),
            atlas_version=str(data.get("atlas_version", "")),
            dependency_hash=str(data.get("dependency_hash", "")),
        )


def _hash_dependency_files(*paths: Path) -> str:
    h = hashlib.sha256()
    for path in paths:
        if path.is_file():
            h.update(path.name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()[:16] if h.digest() else "empty"


def capture_fingerprint(
    *,
    atlas_version: str = "0.6.1",
    project_root: Path | None = None,
) -> EnvironmentFingerprint:
    root = project_root or Path.cwd()
    dep_hash = _hash_dependency_files(
        root / "pyproject.toml",
        root / "requirements.txt",
    )
    return EnvironmentFingerprint(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        atlas_version=atlas_version,
        dependency_hash=dep_hash,
    )


def is_stale(stored: EnvironmentFingerprint, current: EnvironmentFingerprint | None = None) -> bool:
    current = current or capture_fingerprint(atlas_version=stored.atlas_version)
    return (
        stored.python_version != current.python_version
        or stored.dependency_hash != current.dependency_hash
    )


def fingerprint_from_tags(tags: list[str]) -> EnvironmentFingerprint | None:
    for tag in tags:
        if tag.startswith("env_fp:"):
            try:
                return EnvironmentFingerprint.from_dict(json.loads(tag[7:]))
            except (json.JSONDecodeError, TypeError):
                return None
    return None


def fingerprint_tag(fp: EnvironmentFingerprint) -> str:
    return f"env_fp:{json.dumps(fp.to_dict(), sort_keys=True)}"
