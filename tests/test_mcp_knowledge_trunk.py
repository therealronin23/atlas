"""
Tests del F3 del MCP trunk portable: la raíz `knowledge-src` — APIs libres
(Wikipedia) como tools MCP, cableadas a `run_mission` → sustrato verificable.

El bucle único (design doc): knowledge-src (raíz MCP) → run_mission → memoria con
PROCEDENCIA. Honesto: "conocimiento verificable" = procedencia (fuente+fecha+hash),
NO prueba de verdad; el `KnowledgeVerifier` ya filtra grounding.

Capa NEUTRA (`KnowledgeTrunk`): Python puro, fetcher inyectable → sin red en tests.

Diseño: docs/design/mcp_trunk_portable.md (F3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Una respuesta tipo Wikipedia REST summary (sin red: fetcher inyectado).
_WIKI_PAYLOAD = json.dumps(
    {"title": "Atlas", "extract": "Atlas es un titán de la mitología griega."},
    ensure_ascii=False,
)


def _stub_fetcher(captured: list[str] | None = None):
    def fetcher(method: str, url: str, body: bytes | None, headers: dict[str, str]):
        if captured is not None:
            captured.append(url)
        return 200, _WIKI_PAYLOAD

    return fetcher


# ---------------------------------------------------------------------------
# WikipediaSource: respeta el gate SSRF y pega a la REST summary API
# ---------------------------------------------------------------------------


def test_wikipedia_source_hits_summary_api_through_gate() -> None:
    from atlas.knowledge.sources import RawRecord
    from atlas.mcp.knowledge_trunk import WikipediaSource

    seen: list[str] = []
    src = WikipediaSource(fetcher=_stub_fetcher(seen))
    records = src.fetch("Atlas")

    assert len(records) == 1
    rec = records[0]
    assert isinstance(rec, RawRecord)
    assert rec.status == 200  # no bloqueado por SSRF (wikipedia en allowlist de la fuente)
    assert "wikipedia.org" in seen[0]
    assert "/page/summary/Atlas" in seen[0]


# ---------------------------------------------------------------------------
# KnowledgeTrunk: tool de lookup + ingesta cableada al sustrato
# ---------------------------------------------------------------------------


def _trunk(tmp_path: Path):
    from atlas.mcp.knowledge_trunk import KnowledgeTrunk

    return KnowledgeTrunk(tmp_path / "kb", fetcher=_stub_fetcher())


def test_wikipedia_lookup_returns_payload(tmp_path: Path) -> None:
    hits = _trunk(tmp_path).wikipedia("Atlas")
    assert hits and hits[0]["status"] == 200
    assert "titán" in hits[0]["payload"]


def test_ingest_wires_to_substrate_with_provenance(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    report = trunk.ingest_wikipedia("Atlas", domain="knowledge/wikipedia")
    assert report["ingested"] == 1
    assert report["rejected"] == 0
    assert report["ingested_ids"]

    stored = trunk.query("knowledge/wikipedia")
    assert len(stored) == 1
    prov = stored[0]["provenance"]
    # El conocimiento entró con procedencia: fuente + fecha + hash.
    assert "wikipedia.org" in prov["url"]
    assert prov["fetched_at"]
    assert prov["raw_sha256"]


# ---------------------------------------------------------------------------
# Shell FastMCP
# ---------------------------------------------------------------------------


def test_build_knowledge_server_registers_tools(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.knowledge_server import build_knowledge_server

    server = build_knowledge_server(_trunk(tmp_path))
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"wikipedia_lookup", "ingest_wikipedia"} <= names
