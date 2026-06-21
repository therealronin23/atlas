"""
Tests del sembrado del catálogo desde el registro oficial MCP (C paso 4).

`registry.modelcontextprotocol.io` (ya en allowlist SSRF) → candidatos con
PROCEDENCIA. Honesto: todo entra como `candidato` (sin verificar); el prove-it y
el marcado `verificado` son pasos aparte (5). Fetcher inyectable → sin red en tests.

Diseño: docs/design/mcp_trunk_portable.md (F3/knowledge-src) + audit (clasificación).
"""

from __future__ import annotations

import json

# Forma real del API (probada en vivo): servers:[{server:{...}, _meta:{...}}].
_PAYLOAD = json.dumps({
    "servers": [
        {
            "server": {
                "name": "ac.inference.sh/mcp",
                "description": "Run 150+ AI apps",
                "version": "1.0.0",
                "remotes": [{"type": "streamable-http", "url": "https://api.inference.sh/mcp"}],
            },
            "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}},
        },
        {
            "server": {
                "name": "io.github.foo/files",
                "description": "Filesystem server",
                "version": "0.2.0",
                "packages": [{"registryType": "npm", "identifier": "@foo/files"}],
            },
            "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}},
        },
    ],
    "metadata": {},
})


def _stub_fetcher(seen=None):
    def f(method, url, body, headers):
        if seen is not None:
            seen.append(url)
        return 200, _PAYLOAD
    return f


def test_registry_source_hits_official_v0_servers_through_gate() -> None:
    from atlas.knowledge.sources import RawRecord
    from atlas.mcp.registry_seed import RegistrySource

    seen: list[str] = []
    rec = RegistrySource(fetcher=_stub_fetcher(seen)).fetch(None)
    assert isinstance(rec[0], RawRecord) and rec[0].status == 200
    assert "registry.modelcontextprotocol.io" in seen[0]
    assert "/v0/servers" in seen[0]


def test_maps_servers_to_candidates_with_provenance() -> None:
    from atlas.mcp.registry_seed import registry_to_candidates

    cands = registry_to_candidates(json.loads(_PAYLOAD), source_url="https://registry.modelcontextprotocol.io/v0/servers")
    by_name = {c["name"]: c for c in cands}

    a = by_name["ac.inference.sh/mcp"]
    assert a["kind"] == "mcp"
    assert a["status"] == "candidato"        # honesto: sin verificar
    assert a["mode"] == "connected"
    assert a["transport"] == "http"          # tiene remotes streamable-http
    assert a["purpose"] == "Run 150+ AI apps"
    assert a["version"] == "1.0.0"
    assert "registry.modelcontextprotocol.io" in a["provenance"]["source"]
    assert a["provenance"]["fetched_at"]

    b = by_name["io.github.foo/files"]
    assert b["transport"] == "stdio"         # tiene packages, no remotes


def test_candidates_default_uncategorized_sector() -> None:
    from atlas.mcp.registry_seed import registry_to_candidates

    cands = registry_to_candidates(json.loads(_PAYLOAD), source_url="x")
    # Sin clasificar aún: la clasificación por sector es decisión posterior (triaje).
    assert all(c["sector"] == "uncategorized" for c in cands)
