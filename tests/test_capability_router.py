"""Tests Pieza 3 — routing determinista de capacidades."""

from __future__ import annotations

from atlas.mcp.capability_router import (
    format_routing_block,
    invoke_hint,
    route_capabilities,
    routable_entries,
    score_entry,
)
from tests.test_trial_gate import _entry


def _taxonomy() -> dict:
    return {
        "programacion": {
            "label": "Programación",
            "aliases": ["coding", "dev", "react"],
            "subsectors": {
                "frontend": {"label": "Frontend", "aliases": ["react", "next"]},
            },
        },
    }


def test_routable_excludes_candidato() -> None:
    entries = [
        _entry(status="candidato"),
        _entry(name="live", status="instalado"),
    ]
    assert len(routable_entries(entries)) == 1
    assert routable_entries(entries)[0].name == "live"


def test_score_entry_matches_react_in_prompt() -> None:
    entry = _entry(
        name="vercel-react-best-practices",
        status="instalado",
        purpose="patrones React y Next.js",
        tags=["programacion", "frontend"],
        sector="programacion",
    )
    score = score_entry(entry, "necesito revisar componentes react", _taxonomy())
    assert score >= 2.0


def test_route_capabilities_orders_by_score() -> None:
    a = _entry(
        name="vercel-react-best-practices",
        status="instalado",
        purpose="patrones React",
        tags=["programacion"],
        sector="programacion",
    )
    b = _entry(
        name="atlas-memory",
        kind="mcp",
        status="verificado",
        purpose="recall memoria",
        tags=["conocimiento"],
        sector="conocimiento-memoria",
    )
    hits = route_capabilities("optimizar react frontend", [a, b], _taxonomy(), limit=3)
    assert hits
    assert hits[0].name == "vercel-react-best-practices"


def test_route_skips_candidato_even_with_match() -> None:
    entry = _entry(
        name="react-helper",
        status="candidato",
        purpose="react components",
        tags=["programacion"],
    )
    assert route_capabilities("react refactor", [entry], _taxonomy()) == []


def test_format_routing_block_nonempty() -> None:
    hits = route_capabilities(
        "react",
        [_entry(name="vercel-react-best-practices", status="instalado", purpose="react")],
        _taxonomy(),
    )
    block = format_routing_block(hits)
    assert "Capacidades enrutadas" in block
    assert "vercel-react-best-practices" in block


def test_invoke_hint_skill_installed() -> None:
    hint = invoke_hint(_entry(name="foo", status="instalado", mode="installed"))
    assert ".claude/skills/foo" in hint
