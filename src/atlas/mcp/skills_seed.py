"""
Atlas Core — Sembrado de SKILLS desde repos abiertos (GitHub contents API).

Paralelo a `registry_seed` (MCP) pero para "saber" (skills). Fuente estructurada
(NO scraping markdown): el subdir `skills/` de un repo vía api.github.com (ya
allowlisted). Cada dir = un skill instalable con `npx skills add <repo> --skill <n>`
(vercel-labs/skills). Honesto: candidato + procedencia; instalar = consentimiento
+ prove-it. Fetcher inyectable → sin red en tests.

Diseño: docs/design/mcp_trunk_portable.md (Skills ecosystem).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.knowledge.sources import Fetcher, HttpApiSource, RawRecord
from atlas.security.ssrf_bridge import SSRFBridge

_HOST = "api.github.com"


class SkillsSource(HttpApiSource):
    """Lista el subdir `skills/` de un repo GitHub (contents API)."""

    def __init__(self, *, fetcher: Fetcher | None = None) -> None:
        super().__init__(
            "skills-github",
            "skills/github",
            bridge=SSRFBridge(extra_allowed={_HOST}),
            fetcher=fetcher,
        )

    def fetch(self, query: Any) -> list[RawRecord]:
        repo = str(query).strip()
        url = f"https://{_HOST}/repos/{repo}/contents/skills"
        return [self._request("GET", url)]


def skills_to_candidates(payload: list[dict[str, Any]], *, repo: str) -> list[dict[str, Any]]:
    """Mapea los dirs de `skills/` → entradas candidatas (kind=skill, mode=installed)
    con su comando `npx skills add` y procedencia. Sin clasificar (uncategorized)."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    src = f"https://github.com/{repo}"
    out: list[dict[str, Any]] = []
    for item in payload:
        if item.get("type") != "dir":
            continue
        name = item.get("name")
        if not name:
            continue
        out.append({
            "name": name,
            "sector": "uncategorized",
            "kind": "skill",
            "mode": "installed",
            "purpose": "",
            "source": repo,
            "install": f"npx skills add {repo} --skill {name}",
            "status": "candidato",
            "tags": [],
            "provenance": {"source": src, "fetched_at": fetched_at},
        })
    return out
