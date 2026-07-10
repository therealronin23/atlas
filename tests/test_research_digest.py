"""Tests for src/atlas/core/self_maintenance/research_digest.py."""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import yaml

from atlas.core.self_maintenance.research_digest import (
    CandidateSuggestion,
    Finding,
    append_candidates_to_catalog,
    digest_findings,
    parse_findings,
)
from atlas.mcp.catalog import CatalogEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(name: str, *, source: str = "", install: str = "") -> CatalogEntry:
    return CatalogEntry(
        name=name,
        sector="s",
        sector_label="S",
        kind="mcp",
        purpose="",
        source=source,
        install=install,
        status="candidato",
        tags=[],
        mode="connected",
    )


_TAXONOMY: dict[str, Any] = {
    "conocimiento-memoria": {
        "label": "Conocimiento y memoria",
        "desc": "",
        "aliases": ["knowledge", "graph", "memory"],
        "subsectors": {},
    },
    "programacion": {
        "label": "Programación",
        "desc": "",
        "aliases": ["coding", "repository"],
        "subsectors": {},
    },
}


# ---------------------------------------------------------------------------
# parse_findings — formato real de docs/knowledge/research_*.md
# ---------------------------------------------------------------------------

# Fragmento copiado literalmente de docs/knowledge/research_2026-07-10.md
# (secciones consecutivas del mismo tema, una de ellas sin '- extracto:').
_REAL_REPORT_FRAGMENT = textwrap.dedent(
    """\
    # Investigación autónoma — 2026-07-10

    status: propuesto

    Semillas (3): recall_multihop NO es un grafo; Kuzu está libre para KG temporal
    Consultas expandidas (2): temporal knowledge graph, multihop query optimization

    ## Hallazgos (3)

    ### [github] visterion/HiveMem
    - tema: temporal knowledge graph
    - url: https://github.com/visterion/HiveMem
    - extracto: Personal knowledge system — MCP server with PostgreSQL semantic search and temporal knowledge graph

    ### [hackernews] Verígrafo – Temporal Knowledge Graph over Spain's 330K+ official government docs
    - tema: temporal knowledge graph
    - url: https://verigrafo.com/

    ### [github] phvv-me/aizk
    - tema: temporal knowledge graph
    - url: https://github.com/phvv-me/aizk
    - extracto: Self-hosted shared-brain memory engine: multi-tenant bi-temporal knowledge graph with in-database RLS, hybrid retrieval, and MCP
    """
)


def test_parse_findings_real_format() -> None:
    """Parsea el fragmento real: 3 secciones, orden preservado, extracto
    ausente en la sección hackernews que no lo trae."""
    findings = parse_findings(_REAL_REPORT_FRAGMENT)
    assert [f.source for f in findings] == ["github", "hackernews", "github"]
    assert findings[0] == Finding(
        source="github",
        title="visterion/HiveMem",
        url="https://github.com/visterion/HiveMem",
        topic="temporal knowledge graph",
        excerpt=(
            "Personal knowledge system — MCP server with PostgreSQL semantic "
            "search and temporal knowledge graph"
        ),
    )
    assert findings[1].url == "https://verigrafo.com/"
    assert findings[1].excerpt == ""  # sin línea '- extracto:' -> vacío, no crash
    assert findings[2].title == "phvv-me/aizk"


def test_parse_findings_empty_report() -> None:
    assert parse_findings("# Investigación\n\nstatus: propuesto\n\nSin hallazgos.\n") == []


# ---------------------------------------------------------------------------
# digest_findings — señal, dedupe, sector, kind
# ---------------------------------------------------------------------------

def _report(sections: list[tuple[str, str, str, str]]) -> str:
    """Construye un informe crudo mínimo a partir de (source, title, topic, extracto)."""
    lines = ["# Investigación autónoma — test", "", "status: propuesto", "", "## Hallazgos", ""]
    for source, title, topic, excerpt in sections:
        lines.append(f"### [{source}] {title}")
        lines.append(f"- tema: {topic}")
        lines.append(f"- url: https://github.com/{title}")
        if excerpt:
            lines.append(f"- extracto: {excerpt}")
        lines.append("")
    return "\n".join(lines)


def test_digest_signal_two_topics_same_report() -> None:
    """Mismo repo, 2 temas distintos en el MISMO informe -> pasa la señal."""
    report = _report([
        ("github", "acme/graphdb", "temporal knowledge graph", "a KG server"),
        ("github", "acme/graphdb", "graph database benchmark", "a KG server"),
    ])
    result = digest_findings([report], [], _TAXONOMY)
    assert len(result) == 1
    assert result[0].name == "acme/graphdb"
    assert result[0].status == "candidato"


def test_digest_signal_two_reports_same_topic() -> None:
    """Mismo repo, mismo tema, pero en 2 INFORMES distintos -> también pasa la señal."""
    report_a = _report([("github", "acme/graphdb", "knowledge graph", "")])
    report_b = _report([("github", "acme/graphdb", "knowledge graph", "")])
    result = digest_findings([report_a, report_b], [], _TAXONOMY)
    assert len(result) == 1
    assert set(e for e in result[0].evidence if e.startswith("informe:")) == {"informe:0", "informe:1"}


def test_digest_no_signal_zero_suggestions() -> None:
    """Un solo hallazgo, un solo tema, un solo informe -> NO hay señal -> []."""
    report = _report([("github", "acme/oneoff", "temporal knowledge graph", "")])
    assert digest_findings([report], [], _TAXONOMY) == []


def test_digest_ignores_non_github_sources() -> None:
    """hackernews/arxiv nunca generan candidato, ni con señal repetida."""
    report = _report([
        ("hackernews", "acme/notreal", "temporal knowledge graph", ""),
        ("hackernews", "acme/notreal", "graph database benchmark", ""),
    ])
    assert digest_findings([report], [], _TAXONOMY) == []


def test_digest_dedupe_by_catalog_name() -> None:
    """Repo ya catalogado por NOMBRE exacto -> nunca se re-propone (lección 2026-07-09)."""
    report = _report([
        ("github", "acme/graphdb", "temporal knowledge graph", ""),
        ("github", "acme/graphdb", "graph database benchmark", ""),
    ])
    catalog = [_entry("acme/graphdb")]
    assert digest_findings([report], catalog, _TAXONOMY) == []


def test_digest_dedupe_by_catalog_url() -> None:
    """Repo ya catalogado solo por URL (install trae el clone url) -> tampoco se re-propone."""
    report = _report([
        ("github", "acme/graphdb", "temporal knowledge graph", ""),
        ("github", "acme/graphdb", "graph database benchmark", ""),
    ])
    catalog = [_entry("Human Readable Name", install="git clone https://github.com/acme/graphdb")]
    assert digest_findings([report], catalog, _TAXONOMY) == []


def test_digest_sector_by_taxonomy_alias() -> None:
    """El tema 'knowledge graph' casa el alias 'knowledge' -> sector conocimiento-memoria."""
    report = _report([
        ("github", "acme/kg", "knowledge graph", "a graph"),
        ("github", "acme/kg", "graph persistence", "a graph"),
    ])
    result = digest_findings([report], [], _TAXONOMY)
    assert len(result) == 1
    assert result[0].sector == "conocimiento-memoria"


def test_digest_sector_fallback_uncategorized() -> None:
    """Sin ninguna señal de alias -> 'uncategorized', nunca inventa un sector."""
    report = _report([
        ("github", "acme/mystery", "underwater basket weaving", ""),
        ("github", "acme/mystery", "competitive yodeling", ""),
    ])
    result = digest_findings([report], [], _TAXONOMY)
    assert len(result) == 1
    assert result[0].sector == "uncategorized"


def test_digest_kind_mcp_vs_tool() -> None:
    """kind='mcp' si el extracto menciona MCP/server; si no, 'tool'."""
    report = _report([
        ("github", "acme/mcpserver", "knowledge graph", "an MCP server implementation"),
        ("github", "acme/mcpserver", "graph persistence", "an MCP server implementation"),
        ("github", "acme/plaintool", "knowledge graph", "a CLI helper script"),
        ("github", "acme/plaintool", "graph persistence", "a CLI helper script"),
    ])
    result = {s.name: s for s in digest_findings([report], [], _TAXONOMY)}
    assert result["acme/mcpserver"].kind == "mcp"
    assert result["acme/plaintool"].kind == "tool"


def test_digest_evidence_traces_topics_and_reports() -> None:
    report = _report([
        ("github", "acme/graphdb", "temporal knowledge graph", ""),
        ("github", "acme/graphdb", "graph database benchmark", ""),
    ])
    result = digest_findings([report], [], _TAXONOMY)
    assert "tema:temporal knowledge graph" in result[0].evidence
    assert "tema:graph database benchmark" in result[0].evidence
    assert "informe:0" in result[0].evidence


# ---------------------------------------------------------------------------
# append_candidates_to_catalog — preserva lo existente, añade candidatos
# ---------------------------------------------------------------------------

_EXISTING_CLASSIFIED_YAML = textwrap.dedent(
    """\
    _generated:
      by: scripts/mcp_sync.py
      at: '2026-07-02T06:08:58.788813+00:00'
    sectors:
      ciberseguridad:
        label: Ciberseguridad
        entries:
        - name: ai.aliengiraffe/spotdb
          kind: mcp
          subsector: ''
          mode: connected
          source: ai.aliengiraffe/spotdb
          install: ''
          status: candidato
          tags:
          - uncategorized
    """
)


def test_append_adds_to_existing_sector(tmp_path: Path) -> None:
    path = tmp_path / "classified.yaml"
    path.write_text(_EXISTING_CLASSIFIED_YAML, encoding="utf-8")

    suggestions = [
        CandidateSuggestion(
            name="acme/graphdb",
            url="https://github.com/acme/graphdb",
            sector="ciberseguridad",
            kind="tool",
            evidence=("tema:knowledge graph", "informe:0"),
        )
    ]
    added = append_candidates_to_catalog(suggestions, path)
    assert added == 1

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data["sectors"]["ciberseguridad"]["entries"]
    assert len(entries) == 2
    assert entries[1]["name"] == "acme/graphdb"
    assert entries[1]["status"] == "candidato"
    assert entries[1]["provenance"]["source"] == "research_digest"
    assert "fetched_at" in entries[1]["provenance"]


def test_append_creates_new_sector_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "classified.yaml"
    path.write_text(_EXISTING_CLASSIFIED_YAML, encoding="utf-8")

    suggestions = [
        CandidateSuggestion(
            name="acme/kg",
            url="https://github.com/acme/kg",
            sector="conocimiento-memoria",
            kind="mcp",
            evidence=(),
        )
    ]
    append_candidates_to_catalog(suggestions, path)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "conocimiento-memoria" in data["sectors"]
    new_entries = data["sectors"]["conocimiento-memoria"]["entries"]
    assert len(new_entries) == 1
    assert new_entries[0]["name"] == "acme/kg"
    assert new_entries[0]["mode"] == "connected"  # kind=mcp -> connected


def test_append_never_installs_status() -> None:
    suggestion = CandidateSuggestion(
        name="acme/x", url="https://github.com/acme/x", sector="s", kind="tool", evidence=(),
    )
    assert suggestion.status == "candidato"


def test_append_preserves_existing_entries_byte_for_byte(tmp_path: Path) -> None:
    """Las entradas PRE-EXISTENTES sobreviven byte-a-byte en claves y valores
    tras el append (round-trip YAML) — no se reescribe ni se pierde nada."""
    path = tmp_path / "classified.yaml"
    path.write_text(_EXISTING_CLASSIFIED_YAML, encoding="utf-8")
    before = yaml.safe_load(_EXISTING_CLASSIFIED_YAML)
    original_entry = before["sectors"]["ciberseguridad"]["entries"][0]

    suggestions = [
        CandidateSuggestion(
            name="new/one", url="https://github.com/new/one", sector="ciberseguridad",
            kind="tool", evidence=(),
        )
    ]
    append_candidates_to_catalog(suggestions, path)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    survived = after["sectors"]["ciberseguridad"]["entries"][0]
    assert survived == original_entry
    for key, value in original_entry.items():
        assert survived[key] == value


def test_append_zero_suggestions_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "classified.yaml"
    path.write_text(_EXISTING_CLASSIFIED_YAML, encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    assert append_candidates_to_catalog([], path) == 0
    assert path.read_text(encoding="utf-8") == before
