"""Eslabón de DIGESTIÓN del ciclo de investigación abierta (Fase 4 → Fase 5).

``PanoramaScout``/``TopicExpander`` producen informes crudos en
``docs/knowledge/research_*.md`` (renderizados por
``_render_research_report`` en ``orchestrator_parts/maintenance_facade.py``,
formato: ``### [source] title`` + ``- tema:`` / ``- url:`` / ``- extracto:``).
Este módulo cierra el lazo: lee esos informes ya escritos y propone
CANDIDATOS de catálogo MCP — nunca instala nada (wire-before-claim, ADR-039).

Todo aquí es función PURA: sin red, sin LLM, sin logging. Determinista por
diseño para que sea fácil de auditar y de testear. Reglas duras:

- Solo cuentan hallazgos ``[github]`` (los demás — hackernews/arxiv — son
  ruido de descubrimiento, no candidatos instalables).
- Señal mínima: el mismo repo debe aparecer en ≥2 temas DISTINTOS dentro de
  un informe, o en ≥2 informes DISTINTOS. Un repo que aparece una sola vez
  en un solo tema es casualidad de búsqueda, no señal.
- Dedupe fail-closed contra el catálogo YA existente, por NOMBRE y por URL —
  lección real 2026-07-09: un duplicado costó una propuesta rechazada. Ver
  ``_catalog_identity_keys``.
- Sector por alias del taxonomy (reutiliza ``atlas.mcp.catalog.classify``,
  no reinventa el matching). Sin señal → ``uncategorized`` (honesto).
- Toda sugerencia nace con ``status='candidato'`` — jamás otro estado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from atlas.mcp.catalog import CatalogEntry, classify

# ---------------------------------------------------------------------------
# Parseo del informe
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^### \[(?P<source>[^\]]+)\]\s*(?P<title>.+?)\s*$")
_TEMA_PREFIX = "- tema:"
_URL_PREFIX = "- url:"
_EXTRACTO_PREFIX = "- extracto:"


@dataclass(frozen=True)
class Finding:
    """Un hallazgo ya parseado de un informe ``research_*.md``."""

    source: str
    title: str
    url: str
    topic: str
    excerpt: str


def parse_findings(report_text: str) -> list[Finding]:
    """Parsea el formato real de ``_render_research_report``: secciones
    ``### [source] title`` seguidas de líneas ``- tema:``/``- url:``/
    ``- extracto:`` (el extracto es opcional — algunos hallazgos HN no lo
    traen). Robusto a líneas en blanco y a metadata previa (semillas,
    consultas expandidas, cabecera)."""
    findings: list[Finding] = []
    current: dict[str, str] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.get("source") and current.get("title"):
            findings.append(
                Finding(
                    source=current.get("source", ""),
                    title=current.get("title", ""),
                    url=current.get("url", ""),
                    topic=current.get("topic", ""),
                    excerpt=current.get("excerpt", ""),
                )
            )
        current = None

    for line in report_text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            flush()
            current = {"source": m.group("source").strip(), "title": m.group("title").strip()}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith(_TEMA_PREFIX):
            current["topic"] = stripped[len(_TEMA_PREFIX):].strip()
        elif stripped.startswith(_URL_PREFIX):
            current["url"] = stripped[len(_URL_PREFIX):].strip()
        elif stripped.startswith(_EXTRACTO_PREFIX):
            current["excerpt"] = stripped[len(_EXTRACTO_PREFIX):].strip()
    flush()
    return findings


# ---------------------------------------------------------------------------
# Digestión → candidatos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateSuggestion:
    """Sugerencia de candidato de catálogo — SIEMPRE ``status='candidato'``.

    ``evidence`` traza de dónde salió la señal: entradas ``tema:<topic>`` y
    ``informe:<índice>`` (índice posicional dentro de la lista ``reports``
    pasada a ``digest_findings``), para poder auditar por qué se propuso."""

    name: str
    url: str
    sector: str
    kind: str
    evidence: tuple[str, ...]
    status: str = "candidato"


# owner/repo embebido en una URL/instalador de github.com, tolerante a
# ``.git`` final y a lo que venga después (branch, query, fragment).
_GITHUB_REPO_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?:[/?#]|\s|$)", re.IGNORECASE)

_MCP_HINT_RE = re.compile(r"\bmcp\b|\bserver\b", re.IGNORECASE)


def _catalog_identity_keys(catalog: list[CatalogEntry]) -> tuple[set[str], set[str]]:
    """Normaliza el catálogo a dos conjuntos de claves en minúsculas para
    dedupe fail-closed: ``names`` (nombre de entrada del catálogo Y todo
    owner/repo detectable en ``source``/``install``) y ``urls`` (URL completa
    de github.com reconstruida a partir de esos mismos owner/repo). Nunca se
    re-propone nada que case contra cualquiera de los dos conjuntos."""
    names: set[str] = set()
    urls: set[str] = set()
    for entry in catalog:
        names.add(entry.name.strip().lower())
        for field_value in (entry.source, entry.install):
            if not field_value:
                continue
            m = _GITHUB_REPO_RE.search(field_value)
            if m:
                repo = m.group(1).strip("/").lower()
                names.add(repo)
                urls.add(f"https://github.com/{repo}")
    return names, urls


def _is_cataloged(name: str, url: str, cat_names: set[str], cat_urls: set[str]) -> bool:
    norm_url = url.strip().rstrip("/").lower()
    return name.strip().lower() in cat_names or norm_url in cat_urls


@dataclass
class _Aggregate:
    url: str = ""
    topics: set[str] = field(default_factory=set)
    reports: set[int] = field(default_factory=set)
    excerpts: list[str] = field(default_factory=list)


def digest_findings(
    reports: list[str],
    catalog: list[CatalogEntry],
    taxonomy: dict[str, Any],
) -> list[CandidateSuggestion]:
    """Digiere una lista de informes crudos (texto completo de cada
    ``research_*.md``) en sugerencias de candidato deterministas.

    Nota de firma: el diseño original pedía ``digest_findings(reports,
    catalog)``; la clasificación de sector por alias exige el ``taxonomy``
    (``load_taxonomy``) así que se añade como tercer parámetro explícito —
    ver desviación documentada en el reporte de la tarea.
    """
    aggregates: dict[str, _Aggregate] = {}
    for report_idx, report_text in enumerate(reports):
        for finding in parse_findings(report_text):
            if finding.source != "github":
                continue
            name = finding.title.strip()
            if not name:
                continue
            agg = aggregates.setdefault(name, _Aggregate())
            if not agg.url and finding.url:
                agg.url = finding.url
            if finding.topic:
                agg.topics.add(finding.topic)
            agg.reports.add(report_idx)
            if finding.excerpt:
                agg.excerpts.append(finding.excerpt)

    cat_names, cat_urls = _catalog_identity_keys(catalog)

    suggestions: list[CandidateSuggestion] = []
    for name in sorted(aggregates):
        agg = aggregates[name]
        has_signal = len(agg.topics) >= 2 or len(agg.reports) >= 2
        if not has_signal:
            continue
        if _is_cataloged(name, agg.url, cat_names, cat_urls):
            continue

        combined_excerpt = " ".join(agg.excerpts)
        sector = classify(name, combined_excerpt, sorted(agg.topics), taxonomy)
        kind = "mcp" if _MCP_HINT_RE.search(combined_excerpt) else "tool"

        evidence = tuple(
            sorted(f"tema:{t}" for t in agg.topics)
            + sorted(f"informe:{i}" for i in agg.reports)
        )
        suggestions.append(
            CandidateSuggestion(
                name=name,
                url=agg.url,
                sector=sector,
                kind=kind,
                evidence=evidence,
            )
        )
    return suggestions


# ---------------------------------------------------------------------------
# Append al catálogo clasificado (nunca instala — solo registra candidatos)
# ---------------------------------------------------------------------------

_MODE_BY_KIND = {"mcp": "connected", "tool": "installed"}


def append_candidates_to_catalog(
    suggestions: list[CandidateSuggestion], classified_path: Path
) -> int:
    """Añade ``suggestions`` al final del sector correspondiente en
    ``mcp_catalog_classified.yaml``, vía round-trip YAML (igual que
    ``apply_status_promotions`` en ``atlas.mcp.catalog``): el anidado
    sector→entries hace el append textual no-trivial en el caso general
    (sector puede no existir todavía). Preserva TAL CUAL el contenido
    existente — solo añade, nunca reescribe una entrada previa.

    ``status`` es siempre ``'candidato'`` (nunca instala, wire-before-claim).
    Devuelve cuántas entradas se añadieron."""
    if not suggestions:
        return 0

    data: dict[str, Any] = yaml.safe_load(classified_path.read_text(encoding="utf-8")) or {}
    sectors: dict[str, Any] = data.setdefault("sectors", {})

    fetched_at = datetime.now(timezone.utc).isoformat()
    added = 0
    for s in suggestions:
        block = sectors.setdefault(s.sector, {})
        if "label" not in block:
            block["label"] = s.sector
        entries: list[Any] = block.setdefault("entries", [])
        entries.append(
            {
                "name": s.name,
                "kind": s.kind,
                "subsector": "",
                "mode": _MODE_BY_KIND.get(s.kind, "installed"),
                "source": s.url,
                "install": "",
                "status": s.status,
                "tags": [s.sector],
                "evidence": list(s.evidence),
                "provenance": {"source": "research_digest", "fetched_at": fetched_at},
            }
        )
        added += 1

    classified_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return added
