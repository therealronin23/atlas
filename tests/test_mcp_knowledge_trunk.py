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


# Una respuesta tipo World Bank API (array JSON: [metadata, [filas]]).
_WB_PAYLOAD = json.dumps(
    [
        {"page": 1, "total": 1},
        [{"country": {"value": "Spain"}, "date": "2022", "value": 47558630}],
    ],
    ensure_ascii=False,
)


def _wb_fetcher(captured: list[str] | None = None):
    def fetcher(method: str, url: str, body: bytes | None, headers: dict[str, str]):
        if captured is not None:
            captured.append(url)
        return 200, _WB_PAYLOAD

    return fetcher


def test_worldbank_source_hits_indicator_api_through_gate() -> None:
    from atlas.knowledge.sources import RawRecord
    from atlas.mcp.knowledge_trunk import WorldBankSource

    seen: list[str] = []
    src = WorldBankSource(fetcher=_wb_fetcher(seen))
    records = src.fetch({"country": "ES", "indicator": "SP.POP.TOTL"})

    assert len(records) == 1
    assert isinstance(records[0], RawRecord)
    assert records[0].status == 200
    assert "api.worldbank.org" in seen[0]
    assert "/country/ES/indicator/SP.POP.TOTL" in seen[0]
    assert "format=json" in seen[0]


def test_ingest_worldbank_wires_to_substrate_with_provenance(tmp_path: Path) -> None:
    from atlas.mcp.knowledge_trunk import KnowledgeTrunk

    trunk = KnowledgeTrunk(tmp_path / "kb", fetcher=_wb_fetcher())
    report = trunk.ingest_worldbank("ES", "SP.POP.TOTL", domain="knowledge/worldbank")
    assert report["ingested"] == 1
    assert report["rejected"] == 0

    stored = trunk.query("knowledge/worldbank")
    assert len(stored) == 1
    prov = stored[0]["provenance"]
    assert "api.worldbank.org" in prov["url"]
    assert prov["fetched_at"] and prov["raw_sha256"]


def _json_fetcher(payload: str, seen=None):
    def f(method, url, body, headers):
        if seen is not None:
            seen.append(url)
        return 200, payload
    return f


def test_open_meteo_source_hits_forecast_api_through_gate() -> None:
    from atlas.knowledge.sources import RawRecord
    from atlas.mcp.knowledge_trunk import OpenMeteoSource

    seen: list[str] = []
    src = OpenMeteoSource(fetcher=_json_fetcher('{"latitude":40.4}', seen))
    rec = src.fetch({"latitude": 40.4, "longitude": -3.7})
    assert isinstance(rec[0], RawRecord) and rec[0].status == 200
    assert "api.open-meteo.com" in seen[0]
    assert "latitude=40.4" in seen[0] and "longitude=-3.7" in seen[0]


def test_frankfurter_source_hits_rates_api_through_gate() -> None:
    from atlas.mcp.knowledge_trunk import FrankfurterSource

    seen: list[str] = []
    src = FrankfurterSource(fetcher=_json_fetcher('{"rates":{"EUR":0.87}}', seen))
    rec = src.fetch({"from": "USD", "to": "EUR"})
    assert rec[0].status == 200
    assert "api.frankfurter.app" in seen[0]
    assert "from=USD" in seen[0] and "to=EUR" in seen[0]


def test_ingest_open_meteo_and_frankfurter_with_provenance(tmp_path: Path) -> None:
    from atlas.mcp.knowledge_trunk import KnowledgeTrunk

    t1 = KnowledgeTrunk(tmp_path / "k1", fetcher=_json_fetcher('{"latitude":40.4,"x":1}'))
    r1 = t1.ingest_open_meteo(40.4, -3.7)
    assert r1["ingested"] == 1
    assert "api.open-meteo.com" in t1.query("knowledge/open-meteo")[0]["provenance"]["url"]

    t2 = KnowledgeTrunk(tmp_path / "k2", fetcher=_json_fetcher('{"rates":{"EUR":0.87},"y":2}'))
    r2 = t2.ingest_frankfurter("USD", "EUR")
    assert r2["ingested"] == 1
    assert "api.frankfurter.app" in t2.query("knowledge/frankfurter")[0]["provenance"]["url"]


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
    assert {"worldbank_lookup", "ingest_worldbank"} <= names
