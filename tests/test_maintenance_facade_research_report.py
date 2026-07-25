"""Tests for optional seed rendering in research reports."""
from __future__ import annotations

from atlas.core.orchestrator_parts.maintenance_facade import _render_research_report
from atlas.core.self_maintenance.panorama_scout import PanoramaFinding


def test_render_includes_seed_line_when_present() -> None:
    finding = PanoramaFinding(
        topic="temporal knowledge graph", source="github", title="acme/mempalace",
        url="https://github.com/acme/mempalace", excerpt="a tool",
        seed="memoria de agentes de IA",
    )
    lines = _render_research_report("2026-07-25", ["seed"], ["query"], [finding]).splitlines()
    topic_index = next(i for i, line in enumerate(lines) if line.startswith("- tema:"))
    assert lines[topic_index + 1] == "- seed: memoria de agentes de IA"


def test_render_omits_seed_line_when_absent() -> None:
    finding = PanoramaFinding(
        topic="temporal knowledge graph", source="github", title="acme/mempalace",
        url="https://github.com/acme/mempalace", excerpt="a tool",
    )
    assert "- seed:" not in _render_research_report("2026-07-25", ["seed"], ["query"], [finding])
