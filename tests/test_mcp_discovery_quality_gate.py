from __future__ import annotations

from atlas.core.self_maintenance.mcp_discovery_quality_gate import QualityVerdict, run_quality_gate, summarize_catalog_capabilities
from atlas.core.self_maintenance.research_digest import CandidateSuggestion
from atlas.mcp.catalog import CatalogEntry


def _candidate(seeds: tuple[str, ...] = ()) -> CandidateSuggestion:
    return CandidateSuggestion("acme/x", "https://github.com/acme/x", "memory", "tool", ("tema:x",), seeds=seeds)


def test_gate_requires_a_real_seed_relevant_capability_gap() -> None:
    keep = run_quality_gate([_candidate()], capability_summary="", judge_fn=lambda _c, _x: QualityVerdict(True, True, False, "ok"))
    reject = run_quality_gate([_candidate()], capability_summary="", judge_fn=lambda _c, _x: QualityVerdict(False, True, True, "toy"))
    assert keep == []
    assert reject == []


def test_gate_fails_closed_and_passes_seed_to_judge() -> None:
    seen: list[str] = []
    def crashing_judge(_candidate, context):
        seen.append(context.seed)
        raise RuntimeError("down")
    assert run_quality_gate([_candidate(("agent memory",))], capability_summary="", judge_fn=crashing_judge) == []
    assert seen == ["agent memory"]


def test_capability_summary_counts_only_installed_and_verified() -> None:
    entries = [
        CatalogEntry("a", "memory", "Memory", "mcp", "", "", "", "instalado", [], "connected"),
        CatalogEntry("b", "memory", "Memory", "mcp", "", "", "", "verificado", [], "connected"),
        CatalogEntry("c", "memory", "Memory", "mcp", "", "", "", "candidato", [], "connected"),
    ]
    assert "memory: 2" in summarize_catalog_capabilities(entries)
