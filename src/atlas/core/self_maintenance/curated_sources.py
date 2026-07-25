"""Operator-curated GitHub sources for the normal discovery pipeline.

Curated URLs receive no trust bypass: malformed, absent, or non-GitHub input
is ignored and every returned finding still goes through digest and vetting.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding

_GITHUB_REPO_RE = re.compile(
    r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?:[/?#]|\s|$)", re.IGNORECASE
)


def load_curated_findings(path: Path) -> list[PanoramaFinding]:
    """Load valid GitHub repository URLs from optional YAML, fail-closed."""
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    sources = data.get("sources", []) if isinstance(data, dict) else []
    findings: list[PanoramaFinding] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        note = str(entry.get("note", "")).strip()
        match = _GITHUB_REPO_RE.search(url)
        if not match:
            continue
        findings.append(PanoramaFinding(
            topic=f"curated: {note}" if note else "curated",
            source="github", title=match.group(1), url=url, excerpt=note,
        ))
    return findings
