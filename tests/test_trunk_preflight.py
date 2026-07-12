from __future__ import annotations

from pathlib import Path

from atlas.core.trunk_preflight import build_trunk_preflight_section


def test_preflight_section_is_fail_open_without_catalog(tmp_path: Path) -> None:
    assert build_trunk_preflight_section(tmp_path, "refactor graph") == ""


def test_preflight_section_uses_repo_catalog() -> None:
    repo = Path(__file__).resolve().parent.parent
    section = build_trunk_preflight_section(repo, "refactor atlas graph", limit=4)

    assert "## Trunk preflight" in section
    assert "catalog://manifest" in section
    assert "atlas-graph" in section
    assert "candidate-only" in section or "usable" in section
