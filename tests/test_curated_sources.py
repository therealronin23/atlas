from __future__ import annotations

from pathlib import Path

import yaml

from atlas.core.self_maintenance.curated_sources import load_curated_findings


def test_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_curated_findings(tmp_path / "nope.yaml") == []


def test_loads_github_url_as_finding(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(yaml.safe_dump({"sources": [{"url": "https://github.com/vercel-labs/agent-skills", "note": "Vercel skills registry"}]}), encoding="utf-8")
    finding = load_curated_findings(path)[0]
    assert (finding.source, finding.title, finding.excerpt, finding.topic) == ("github", "vercel-labs/agent-skills", "Vercel skills registry", "curated: Vercel skills registry")


def test_non_github_or_malformed_input_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text("sources:\n  - url: https://tododeia.com/community\n", encoding="utf-8")
    assert load_curated_findings(path) == []
    path.write_text("not: [valid, yaml:", encoding="utf-8")
    assert load_curated_findings(path) == []
