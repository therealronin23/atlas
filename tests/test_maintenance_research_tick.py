"""Integration seams for the opt-in research tick."""
from __future__ import annotations

from pathlib import Path

from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance.panorama_scout import PanoramaFinding
from atlas.core.self_maintenance.topic_expander import TopicExpansion


def test_research_tick_threads_seed_and_min_stars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    monkeypatch.setenv("ATLAS_MCP_DISCOVERY_MIN_STARS", "7")
    (tmp_path / "core").mkdir()
    (tmp_path / "atlas").mkdir()

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            assert queries_per_seed == 4
            return [TopicExpansion(seed="memoria de agentes de IA", queries=["agent memory"])]

    seen: dict[str, object] = {}
    class Scout:
        def __init__(self, **kwargs) -> None: seen.update(kwargs)
        def discover(self):
            return [PanoramaFinding(topic="agent memory", source="github", title="acme/memory", url="https://github.com/acme/memory", excerpt="x", seed=seen["topic_seeds"]["agent memory"])]

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert result["status"] == "ran"
    assert seen["min_stars"] == 7
    assert "- seed: memoria de agentes de IA" in report


def test_research_tick_includes_curated_findings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "core" / "docs" / "knowledge").mkdir(parents=True)
    (tmp_path / "atlas").mkdir()
    (tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml").write_text(
        "sources:\n  - url: https://github.com/vercel-labs/agent-skills\n    note: Vercel skills\n",
        encoding="utf-8",
    )
    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="x", queries=["x"])]
    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return []
    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    assert "vercel-labs/agent-skills" in Path(result["report_path"]).read_text(encoding="utf-8")
