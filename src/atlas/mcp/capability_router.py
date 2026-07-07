"""
Atlas Core — Pieza 3: routing determinista de capacidades.

Selecciona del catálogo enriquecido las entradas USABLES (instalado/verificado/
probado-en-jaula) que casan con el prompt del usuario. Sin LLM — reglas + score.

Diseño: docs/design/design_catalog_enrichment.md (Pieza 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from atlas.mcp.catalog import CatalogEntry

_ROUTABLE = frozenset({"instalado", "verificado", "probado-en-jaula"})
_MATURITY_BONUS = {"instalado": 0.5, "verificado": 0.3, "probado-en-jaula": 0.1}
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)


@dataclass(frozen=True)
class RouteHit:
    name: str
    kind: str
    sector: str
    status: str
    purpose: str
    invoke_hint: str
    score: float

    def to_dict(self) -> dict[str, str | float]:
        return {
            "name": self.name,
            "kind": self.kind,
            "sector": self.sector,
            "status": self.status,
            "purpose": self.purpose,
            "invoke_hint": self.invoke_hint,
            "score": round(self.score, 2),
        }


def routable_entries(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Solo entradas graduadas — nunca ``candidato`` (wire-before-claim)."""
    return [e for e in entries if e.status in _ROUTABLE]


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def invoke_hint(entry: CatalogEntry) -> str:
    if entry.kind == "skill":
        if entry.mode == "served":
            return f"get_skill({entry.name!r}) vía tronco MCP"
        return f".claude/skills/{entry.name}/SKILL.md"
    if entry.kind == "mcp":
        return f"trunk_invoke (sector={entry.sector}, server={entry.name})"
    if entry.kind == "api":
        return f"knowledge MCP / ingest ({entry.name})"
    if entry.kind == "prompt":
        return f"prompt MCP ({entry.name})"
    return f"catálogo kind={entry.kind} mode={entry.mode}"


def score_entry(
    entry: CatalogEntry,
    prompt: str,
    taxonomy: dict[str, Any],
) -> float:
    """Score determinista: tokens del prompt vs nombre/propósito/tags/alias sector."""
    toks = _tokens(prompt)
    if not toks:
        return 0.0

    score = 0.0
    name_toks = _tokens(entry.name.replace("/", " ").replace("-", " "))
    purpose_toks = _tokens(entry.purpose)
    tag_toks = {t.lower() for t in entry.tags}
    hay = prompt.lower()

    for tok in toks:
        if tok in name_toks or any(tok in nt or nt in tok for nt in name_toks if len(nt) >= 4):
            score += 3.0
        if tok in purpose_toks:
            score += 2.0
        if tok in tag_toks:
            score += 2.0

    sblock = taxonomy.get(entry.sector) or {}
    sector_terms = [entry.sector, str(sblock.get("label", ""))]
    sector_terms.extend(str(a) for a in (sblock.get("aliases") or []))
    for sub in (sblock.get("subsectors") or {}).values():
        sector_terms.append(str(sub.get("label", "")))
        sector_terms.extend(str(a) for a in (sub.get("aliases") or []))

    for term in sector_terms:
        t = term.strip().lower()
        if len(t) >= 3 and re.search(rf"\b{re.escape(t)}\b", hay):
            score += 4.0
            break

    score += _MATURITY_BONUS.get(entry.status, 0.0)
    return score


def route_capabilities(
    prompt: str,
    entries: list[CatalogEntry],
    taxonomy: dict[str, Any],
    *,
    limit: int = 5,
    min_score: float = 2.0,
) -> list[RouteHit]:
    """Devuelve las mejores capacidades enrutables para el prompt."""
    pool = routable_entries(entries)
    scored: list[RouteHit] = []
    for entry in pool:
        s = score_entry(entry, prompt, taxonomy)
        if s < min_score:
            continue
        scored.append(
            RouteHit(
                name=entry.name,
                kind=entry.kind,
                sector=entry.sector,
                status=entry.status,
                purpose=entry.purpose[:120],
                invoke_hint=invoke_hint(entry),
                score=s,
            )
        )
    scored.sort(key=lambda h: (-h.score, h.status, h.name.lower()))
    return scored[:limit]


def format_routing_block(hits: list[RouteHit]) -> str:
    """Bloque markdown inyectado por el hook UserPromptSubmit."""
    if not hits:
        return ""
    lines = [
        "### Capacidades enrutadas (Atlas — determinista, catálogo graduado)",
        "",
        "Usa estas capacidades **antes** de improvisar o buscar externo:",
        "",
    ]
    for i, h in enumerate(hits, 1):
        lines.append(
            f"{i}. **{h.name}** ({h.kind}, {h.status}) — {h.purpose or '(sin purpose)'}"
        )
        lines.append(f"   → {h.invoke_hint}")
    lines.append("")
    return "\n".join(lines)
