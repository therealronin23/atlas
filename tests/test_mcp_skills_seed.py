"""
Tests del sembrado de SKILLS desde repos abiertos (GitHub contents API).

Paralelo al sembrado de MCP, pero para "saber" (skills). Fuente estructurada (no
scraping markdown): GitHub contents API (api.github.com, ya allowlisted) del subdir
`skills/` de un repo. Cada dir = un skill instalable con `npx skills add`.
Honesto: candidato + provenance; instalar = consentimiento + prove-it.

Diseño: docs/design/mcp_trunk_portable.md (Skills ecosystem).
"""

from __future__ import annotations

import json

_PAYLOAD = json.dumps([
    {"name": "react-best-practices", "type": "dir"},
    {"name": "web-design-guidelines", "type": "dir"},
    {"name": "README.md", "type": "file"},
])


def _stub(seen=None):
    def f(method, url, body, headers):
        if seen is not None:
            seen.append(url)
        return 200, _PAYLOAD
    return f


def test_skills_source_hits_github_contents_through_gate() -> None:
    from atlas.knowledge.sources import RawRecord
    from atlas.mcp.skills_seed import SkillsSource

    seen: list[str] = []
    rec = SkillsSource(fetcher=_stub(seen)).fetch("vercel-labs/agent-skills")
    assert isinstance(rec[0], RawRecord) and rec[0].status == 200
    assert "api.github.com" in seen[0]
    assert "vercel-labs/agent-skills/contents/skills" in seen[0]


def test_skills_to_candidates_builds_install_command() -> None:
    from atlas.mcp.skills_seed import skills_to_candidates

    cands = skills_to_candidates(json.loads(_PAYLOAD), repo="vercel-labs/agent-skills")
    by = {c["name"]: c for c in cands}
    assert set(by) == {"react-best-practices", "web-design-guidelines"}  # solo dirs
    c = by["react-best-practices"]
    assert c["kind"] == "skill"
    assert c["mode"] == "installed"
    assert c["status"] == "candidato"
    assert c["install"] == "npx skills add vercel-labs/agent-skills --skill react-best-practices"
    assert "github.com" in c["provenance"]["source"]
