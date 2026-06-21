"""
Atlas Core — Foundation de sembrado POR LÍNEA (C: completar todas las líneas).

Reúne las fuentes de descubrimiento reutilizables para sembrar el catálogo de
CUALQUIER línea (kind) sin duplicar módulos:

- `GithubLineSource(repo, subdir)` + `dirs_to_candidates`: para líneas cuyo repo
  tiene un subdir con un dir por item (skills/prompts/commands/hooks/subagents/
  rules/workflows). Vía GitHub contents API (allowlisted).
- `ApisGuruSource` + `apis_to_candidates`: la línea APIs (directorio OpenAPI
  apis.guru, JSON limpio).

Todo entra `candidato`/`uncategorized` con procedencia. Fetcher inyectable → sin
red en tests. La clasificación por dominio y el prove-it son pasos posteriores.

Diseño: docs/design/mcp_trunk_portable.md (Skills ecosystem) + audit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.knowledge.sources import Fetcher, HttpApiSource, RawRecord
from atlas.security.ssrf_bridge import SSRFBridge

_GH_HOST = "api.github.com"
_APIS_HOST = "api.apis.guru"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# GitHub line (genérico): un dir por item en <repo>/<subdir>
# ---------------------------------------------------------------------------


class GithubLineSource(HttpApiSource):
    def __init__(self, repo: str, subdir: str, *, fetcher: Fetcher | None = None) -> None:
        super().__init__(
            f"gh:{repo}:{subdir}", "line/github",
            bridge=SSRFBridge(extra_allowed={_GH_HOST}), fetcher=fetcher,
        )
        self._repo, self._subdir = repo, subdir

    def fetch(self, query: Any) -> list[RawRecord]:
        url = f"https://{_GH_HOST}/repos/{self._repo}/contents/{self._subdir}"
        return [self._request("GET", url)]


def dirs_to_candidates(
    payload: list[dict[str, Any]], *, repo: str, kind: str, install_template: str,
    sector: str = "uncategorized",
) -> list[dict[str, Any]]:
    """Cada dir del subdir → candidato del `kind` dado, con su `install` (formateado
    con {repo} y {name}) y procedencia."""
    fetched_at, src = _now(), f"https://github.com/{repo}"
    out: list[dict[str, Any]] = []
    for item in payload:
        if item.get("type") != "dir":
            continue
        name = item.get("name")
        if not name:
            continue
        out.append({
            "name": name, "sector": sector, "kind": kind,
            "purpose": "", "source": repo,
            "install": install_template.format(repo=repo, name=name),
            "status": "candidato", "tags": [],
            "provenance": {"source": src, "fetched_at": fetched_at},
        })
    return out


# ---------------------------------------------------------------------------
# APIs (apis.guru): directorio OpenAPI
# ---------------------------------------------------------------------------


class ApisGuruSource(HttpApiSource):
    def __init__(self, *, fetcher: Fetcher | None = None) -> None:
        super().__init__(
            "apis-guru", "line/apis",
            bridge=SSRFBridge(extra_allowed={_APIS_HOST}), fetcher=fetcher,
        )

    def fetch(self, query: Any) -> list[RawRecord]:
        return [self._request("GET", f"https://{_APIS_HOST}/v2/list.json")]


def apis_to_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Cada API del directorio → candidato kind=api (mode served: la envolvemos en
    knowledge-src). Procedencia + categoría como tag."""
    fetched_at = _now()
    out: list[dict[str, Any]] = []
    for name, rec in payload.items():
        pref = rec.get("preferred")
        versions = rec.get("versions", {})
        info = (versions.get(pref) or {}).get("info", {}) if pref else {}
        cats = info.get("x-apisguru-categories") or []
        out.append({
            "name": name, "sector": "uncategorized", "kind": "api", "mode": "served",
            "purpose": (info.get("title") or "") + (
                f" — {info.get('description', '')[:80]}" if info.get("description") else ""),
            "source": name, "install": "", "status": "candidato",
            "tags": [str(c) for c in cats],
            "provenance": {"source": "https://apis.guru", "fetched_at": fetched_at},
        })
    return out
