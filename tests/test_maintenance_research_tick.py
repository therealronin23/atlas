"""Integration seams for the opt-in research tick."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance.panorama_scout import PanoramaFinding
from atlas.core.self_maintenance.topic_expander import TopicExpansion


def test_egress_fetch_uses_checked_pinned_ip(monkeypatch) -> None:
    from atlas.core.orchestrator_parts.maintenance_facade import _egress_fetch_text

    seen: dict[str, object] = {}

    class Response:
        headers = SimpleNamespace(get_content_type=lambda: "text/html")
        def read(self, _limit: int) -> bytes: return b"official material"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, request, *, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            return Response()

    monkeypatch.setattr(
        "atlas.security.executor._build_opener_with_pinned_ip",
        lambda pinned_ip, url, timeout_s: seen.update({"pinned_ip": pinned_ip, "build_url": url, "build_timeout": timeout_s}) or Opener(),
    )
    decision = SimpleNamespace(pinned_ip="93.184.216.34")
    assert _egress_fetch_text("https://developers.openai.com/resources/", decision=decision) == "official material"
    assert seen["pinned_ip"] == "93.184.216.34"
    assert seen["url"] == "https://developers.openai.com/resources/"


def test_egress_fetch_rejects_binary_content_before_reading(monkeypatch) -> None:
    from atlas.core.orchestrator_parts.maintenance_facade import _egress_fetch_text

    class Response:
        headers = SimpleNamespace(get_content_type=lambda: "application/octet-stream")
        def read(self, _limit: int) -> bytes: raise AssertionError("binary body must not be read")
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, _request, *, timeout): return Response()

    monkeypatch.setattr(
        "atlas.security.executor._build_opener_with_pinned_ip",
        lambda *_args: Opener(),
    )
    with pytest.raises(ValueError, match="content type"):
        _egress_fetch_text(
            "https://developers.openai.com/resources/",
            decision=SimpleNamespace(pinned_ip="93.184.216.34"),
        )


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


def test_research_tick_fetches_curated_official_material_via_injected_egress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "core" / "docs" / "knowledge").mkdir(parents=True)
    (tmp_path / "atlas").mkdir()
    (tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml").write_text(
        "publishers:\n  - id: openai\n    domains: [developers.openai.com]\n"
        "sources:\n  - publisher: openai\n    kind: official_docs\n"
        "    url: https://developers.openai.com/resources/\n    note: OpenAI resources\n",
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
    monkeypatch.setattr(
        "atlas.core.orchestrator_parts.maintenance_facade._egress_fetch_text",
        lambda _url, **_kwargs: "<h1>Official material</h1>",
    )
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert result["curated_findings_count"] == 1
    assert "[official] OpenAI resources" in report
    assert "Official material" in report


def test_research_tick_reruns_once_when_curated_manifest_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    manifest = tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("sources: []\n", encoding="utf-8")
    (tmp_path / "atlas").mkdir()

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="x", queries=["x"])]

    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return []

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    orchestrator = Orchestrator(workspace=tmp_path / "atlas")
    assert orchestrator.maintenance_research_tick()["status"] == "ran"
    manifest.write_text("sources: []\n# changed\n", encoding="utf-8")
    assert orchestrator.maintenance_research_tick()["status"] == "ran"
    assert orchestrator.maintenance_research_tick()["status"] == "already_ran_today"
