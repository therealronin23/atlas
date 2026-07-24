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


def test_paginates_until_no_next_cursor() -> None:
    """El registro real es más grande que una página (verificado en vivo:
    2026-07-23, >400 entradas con nextCursor). Sin paginar, el sembrado se
    queda con solo la primera página (100) para siempre."""
    from atlas.mcp.registry_seed import RegistrySource

    pages = {
        None: json.dumps({"servers": [{"server": {"name": "a"}}], "metadata": {"nextCursor": "cursor1"}}),
        "cursor1": json.dumps({"servers": [{"server": {"name": "b"}}], "metadata": {"nextCursor": "cursor2"}}),
        "cursor2": json.dumps({"servers": [{"server": {"name": "c"}}], "metadata": {}}),
    }
    seen_urls: list[str] = []

    def fetcher(method, url, body, headers):
        seen_urls.append(url)
        cursor = None
        if "cursor=" in url:
            cursor = url.split("cursor=", 1)[1].split("&", 1)[0]
        return 200, pages[cursor]

    records = RegistrySource(fetcher=fetcher).fetch(None)
    assert len(records) == 3
    assert "cursor=cursor1" in seen_urls[1]
    assert "cursor=cursor2" in seen_urls[2]


def test_pagination_stops_at_max_pages_safety_cap() -> None:
    """Un registro (o un bug) que nunca deja de dar nextCursor no debe colgar
    el sembrador para siempre."""
    from atlas.mcp.registry_seed import RegistrySource

    def infinite_fetcher(method, url, body, headers):
        return 200, json.dumps({"servers": [], "metadata": {"nextCursor": "always-more"}})

    records = RegistrySource(fetcher=infinite_fetcher, max_pages=3).fetch(None)
    assert len(records) == 3


def test_pagination_stops_on_non_200_page() -> None:
    from atlas.mcp.registry_seed import RegistrySource

    def flaky_fetcher(method, url, body, headers):
        if "cursor=" in url:
            return 500, "error"
        return 200, json.dumps({"servers": [{"server": {"name": "a"}}], "metadata": {"nextCursor": "x"}})

    records = RegistrySource(fetcher=flaky_fetcher).fetch(None)
    assert len(records) == 2
    assert records[0].status == 200
    assert records[1].status == 500


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


def test_stdio_candidate_captures_real_package_install_info() -> None:
    """Fix 2026-07-24 (bloqueaba la etapa 2A de ADR-075): antes, ``install``
    salía SIEMPRE ``""`` -- se descartaba ``packages[].registryType``/
    ``.identifier``/``.version`` y ``repository.url`` que el registro real SÍ
    trae (verificado en vivo contra registry.modelcontextprotocol.io). Sin
    esto no hay forma de saber QUÉ fetchear para un candidato stdio."""
    from atlas.mcp.registry_seed import registry_to_candidates

    cands = registry_to_candidates(json.loads(_PAYLOAD), source_url="x")
    b = next(c for c in cands if c["name"] == "io.github.foo/files")
    assert b["install"] == "npm:@foo/files"
    assert b["package_registry"] == "npm"
    assert b["package_identifier"] == "@foo/files"


def test_http_candidate_has_empty_install_no_package_to_fetch() -> None:
    from atlas.mcp.registry_seed import registry_to_candidates

    cands = registry_to_candidates(json.loads(_PAYLOAD), source_url="x")
    a = next(c for c in cands if c["name"] == "ac.inference.sh/mcp")
    assert a["install"] == ""
    assert a["package_registry"] == ""


def test_repository_url_captured_when_present() -> None:
    from atlas.mcp.registry_seed import registry_to_candidates

    payload = json.dumps({
        "servers": [{
            "server": {
                "name": "ai.adeu/adeu",
                "description": "Automated DOCX Redlining Engine",
                "version": "1.5.2",
                "packages": [{"registryType": "pypi", "identifier": "adeu", "version": "1.5.2"}],
                "repository": {"url": "https://github.com/dealfluence/adeu", "source": "github"},
            },
        }],
        "metadata": {},
    })
    cands = registry_to_candidates(json.loads(payload), source_url="x")
    c = cands[0]
    assert c["install"] == "pypi:adeu==1.5.2"
    assert c["repository_url"] == "https://github.com/dealfluence/adeu"


def test_candidates_default_uncategorized_sector() -> None:
    from atlas.mcp.registry_seed import registry_to_candidates

    cands = registry_to_candidates(json.loads(_PAYLOAD), source_url="x")
    # Sin clasificar aún: la clasificación por sector es decisión posterior (triaje).
    assert all(c["sector"] == "uncategorized" for c in cands)
