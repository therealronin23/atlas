from __future__ import annotations

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.trunk_prepare import prepare_task_context


def _entry(
    name: str,
    *,
    status: str,
    purpose: str = "",
    kind: str = "mcp",
    sector: str = "programacion",
    subsector: str = "testing",
    mode: str = "connected",
    env: tuple[str, ...] = (),
    read_only: tuple[str, ...] = (),
) -> CatalogEntry:
    return CatalogEntry(
        name=name,
        sector=sector,
        sector_label=sector.title(),
        kind=kind,
        purpose=purpose,
        source="",
        install="",
        status=status,
        tags=[sector],
        mode=mode,
        subsector=subsector,
        env_passthrough=env,
        read_only_tools=read_only,
    )


def _taxonomy() -> dict:
    return {
        "programacion": {
            "label": "Programación",
            "desc": "",
            "aliases": ["coding", "refactor"],
            "subsectors": {
                "testing": {"label": "Testing", "aliases": ["tests"]},
                "docs": {"label": "Docs", "aliases": ["documentation"]},
            },
        }
    }


def test_prepare_returns_compact_recommendations_and_resources() -> None:
    entries = [
        _entry("candidate-docs", status="candidato", purpose="coding docs"),
        _entry("atlas-graph", status="instalado", purpose="coding graph refactor"),
    ]
    out = prepare_task_context(
        entries,
        _taxonomy(),
        "refactor coding graph",
        workbench_available=True,
    )

    assert out["status"] == "ready"
    assert out["resources"] == ["catalog://manifest", "workbench://manifest"]
    assert out["recommended"][0]["name"] == "atlas-graph"
    assert out["recommended"][0]["usable_now"] is True
    assert set(out) == {
        "status",
        "goal",
        "recommended",
        "resources",
        "skills",
        "missing",
        "warnings",
        "next_actions",
    }


def test_prepare_marks_candidates_as_discovery_only() -> None:
    entries = [
        _entry("GitHub MCP", status="candidato", purpose="coding git"),
    ]
    out = prepare_task_context(entries, _taxonomy(), "coding git")

    row = out["recommended"][0]
    assert row["usable_now"] is False
    assert row["requires_consent"] is True
    assert out["missing"] == [
        {
            "name": "GitHub MCP",
            "kind": "mcp",
            "reason": "candidate requires prove-it and explicit consent",
            "requires_consent": True,
        }
    ]


def test_prepare_surfaces_env_requirements() -> None:
    entries = [
        _entry(
            "GitHub MCP",
            status="candidato",
            purpose="coding git",
            env=("GITHUB_PERSONAL_ACCESS_TOKEN",),
        ),
    ]
    out = prepare_task_context(entries, _taxonomy(), "coding git")

    assert out["recommended"][0]["requires_env"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert out["missing"][0]["reason"] == "missing env: GITHUB_PERSONAL_ACCESS_TOKEN"


def test_prepare_uses_external_usage_without_self_audit_counts() -> None:
    entries = [
        _entry("atlas-memory", status="instalado", purpose="coding memory"),
        _entry("atlas-graph", status="instalado", purpose="coding graph"),
    ]
    out = prepare_task_context(
        entries,
        _taxonomy(),
        "coding",
        external_counts={
            "mcp__atlas-memory__recall": 7,
            # self-audit counts never arrive here because ToolUsageCounter.external_counts()
            # filters by origin; keep this test focused on the external signal.
        },
    )

    assert out["recommended"][0]["name"] == "atlas-memory"
    assert out["recommended"][0]["usage_external"] == 7


def test_prepare_respects_read_only_declarations() -> None:
    entries = [
        _entry(
            "Playwright / WebApp Testing",
            status="verificado",
            purpose="browser testing",
            read_only=("browser_snapshot",),
        ),
    ]
    out = prepare_task_context(entries, _taxonomy(), "browser testing")

    assert out["recommended"][0]["read_only_tools"] == ["browser_snapshot"]
