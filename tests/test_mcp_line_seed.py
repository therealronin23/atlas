"""
Tests de la FOUNDATION de sembrado por línea (C: completar todas las líneas).

- GithubLineSource + dirs_to_candidates: seeder GENÉRICO para cualquier línea cuyo
  repo tiene un subdir con un dir por item (skills/prompts/hooks/subagents/rules…).
- ApisGuruSource + apis_to_candidates: la línea APIs (directorio OpenAPI apis.guru).

Fetcher inyectable → sin red en tests. Todo entra `candidato`/`uncategorized` con
procedencia. Reusado por subagentes para sembrar cada línea sin duplicar módulos.
"""

from __future__ import annotations

import json

# --- GitHub line (genérico) ---
_GH = json.dumps([
    {"name": "react-best-practices", "type": "dir"},
    {"name": "deploy-to-vercel", "type": "dir"},
    {"name": "README.md", "type": "file"},
])


def _stub(payload, seen=None):
    def f(method, url, body, headers):
        if seen is not None:
            seen.append(url)
        return 200, payload
    return f


def test_github_line_source_targets_repo_subdir() -> None:
    from atlas.mcp.line_seed import GithubLineSource

    seen: list[str] = []
    GithubLineSource("owner/repo", "prompts", fetcher=_stub(_GH, seen)).fetch(None)
    assert "api.github.com/repos/owner/repo/contents/prompts" in seen[0]


def test_files_to_candidates_handles_file_per_item() -> None:
    from atlas.mcp.line_seed import files_to_candidates

    payload = json.dumps([
        {"name": "expert.md", "type": "file"},
        {"name": "coder.txt", "type": "file"},
        {"name": "sub", "type": "dir"},
        {"name": "README.md", "type": "file"},
    ])
    cands = files_to_candidates(
        json.loads(payload), repo="o/r", subdir="prompts", kind="prompt",
        install_template="curl -O https://raw.githubusercontent.com/{repo}/main/prompts/{file}",
    )
    by = {c["name"]: c for c in cands}
    # files (sin extensión en el name), excluye dirs y README
    assert set(by) == {"expert", "coder"}
    assert by["expert"]["kind"] == "prompt"
    assert "prompts/expert.md" in by["expert"]["install"]


def test_dirs_to_candidates_uses_kind_and_install_template() -> None:
    from atlas.mcp.line_seed import dirs_to_candidates

    cands = dirs_to_candidates(
        json.loads(_GH), repo="owner/repo", kind="prompt",
        install_template="npx skills add {repo} --skill {name}",
    )
    by = {c["name"]: c for c in cands}
    assert set(by) == {"react-best-practices", "deploy-to-vercel"}  # solo dirs
    c = by["deploy-to-vercel"]
    assert c["kind"] == "prompt"
    assert c["status"] == "candidato" and c["sector"] == "uncategorized"
    assert c["install"] == "npx skills add owner/repo --skill deploy-to-vercel"
    assert "github.com/owner/repo" in c["provenance"]["source"]


# --- APIs (apis.guru) ---
_APIS = json.dumps({
    "1forge.com": {
        "preferred": "0.0.1",
        "versions": {"0.0.1": {"info": {
            "title": "1Forge Finance APIs", "description": "Forex data",
            "x-apisguru-categories": ["financial"],
        }}},
    },
})


def test_apis_guru_source_hits_list_through_gate() -> None:
    from atlas.mcp.line_seed import ApisGuruSource

    seen: list[str] = []
    rec = ApisGuruSource(fetcher=_stub(_APIS, seen)).fetch(None)
    assert rec[0].status == 200
    assert "apis.guru/v2/list.json" in seen[0]


def test_apis_to_candidates_extracts_title_and_provenance() -> None:
    from atlas.mcp.line_seed import apis_to_candidates

    cands = apis_to_candidates(json.loads(_APIS))
    c = cands[0]
    assert c["name"] == "1forge.com"
    assert c["kind"] == "api"
    assert c["mode"] == "served"
    assert c["status"] == "candidato"
    assert "1Forge" in c["purpose"]
    assert "apis.guru" in c["provenance"]["source"]


# --- Ficheros sembrados por línea (guard de integridad) ---


def test_all_seeded_line_files_load_and_are_candidato() -> None:
    from pathlib import Path

    from atlas.mcp.catalog import load_catalog

    seeded = sorted((Path(__file__).resolve().parent.parent / "docs/design/seeded").glob("*_seeded.yaml"))
    assert seeded, "debe haber ficheros sembrados por línea"
    for p in seeded:
        entries = load_catalog(p)
        assert entries, f"{p.name} vacío"
        # Honesto: lo sembrado entra sin verificar.
        assert all(e.status == "candidato" for e in entries), f"{p.name} tiene no-candidatos"
        # Un fichero por línea = un kind dominante.
        kinds = {e.kind for e in entries}
        assert len(kinds) == 1, f"{p.name} mezcla kinds {kinds}"
