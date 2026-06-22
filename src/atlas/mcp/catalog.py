"""
Atlas Core — Catálogo MCP estructurado (línea B/C: tronco-agregador + catálogo).

Carga `docs/design/mcp_catalog.yaml`: la fuente MÁQUINA del catálogo, clasificada
por SECTOR/necesidad (el eje de clasificación del tronco-agregador). Lo consume el
instalador y, más adelante, el enrutado del tronco (franken-prompt por objetivo →
subconjunto pequeño de raíces del sector relevante).

Honesto: el estado por defecto es `candidato` (sin verificar); el instalador solo
instala `verificado` (wire-before-claim). Esto reemplaza al parser de tablas
markdown de `installer.py` por una fuente estructurada y rica.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_STATES = {"candidato", "verificado", "instalado"}
# Taxonomía completa de "líneas" del ecosistema de extensión (2026): cada kind es
# una línea propia del catálogo (StormMCP por línea).
_KINDS = {
    "skill", "mcp", "api", "tool",          # las 4 originales
    "prompt", "command",                     # plantillas / slash-commands
    "hook", "subagent", "plugin", "rule",    # constructos de cliente
    "workflow",                              # automatización (n8n, etc.)
}
_MODES = {"served", "connected", "installed"}

# Modo operativo por defecto según kind (cuando el YAML no lo declara):
#   served    = lo servimos inline (sin descarga): skills/prompts/commands, APIs envueltas.
#   connected = MCP server (nuestro o externo) al que el tronco se conecta.
#   installed = se coloca en la config del cliente (hooks/subagents/plugins/rules/tools).
_DEFAULT_MODE = {
    "mcp": "connected",
    "api": "served", "skill": "served", "prompt": "served", "command": "served",
    "tool": "installed", "hook": "installed", "subagent": "installed",
    "plugin": "installed", "rule": "installed", "workflow": "installed",
}


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    sector: str
    sector_label: str
    kind: str
    purpose: str
    source: str
    install: str
    status: str
    tags: list[str]
    mode: str
    subsector: str = ""
    phase: int | None = None
    version: str = ""
    license: str = ""
    trust: str = ""
    transport: str = ""


def load_catalog(path: Path) -> list[CatalogEntry]:
    """Carga y valida el YAML → lista plana de entradas con su sector."""
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: list[CatalogEntry] = []
    for sector_id, block in (data.get("sectors") or {}).items():
        label = str((block or {}).get("label", sector_id))
        for raw in (block or {}).get("entries", []) or []:
            status = str(raw.get("status", "candidato"))
            if status not in _STATES:
                raise ValueError(f"estado inválido {status!r} en {raw.get('name')!r}")
            kind = str(raw.get("kind", "")).strip()
            if kind not in _KINDS:
                raise ValueError(f"kind inválido {kind!r} en {raw.get('name')!r}")
            tags = [str(t) for t in (raw.get("tags") or [])] or [str(sector_id)]
            mode = str(raw.get("mode", "") or _DEFAULT_MODE.get(kind, "connected"))
            if mode not in _MODES:
                raise ValueError(f"mode inválido {mode!r} en {raw.get('name')!r}")
            out.append(
                CatalogEntry(
                    name=str(raw["name"]),
                    sector=str(sector_id),
                    sector_label=label,
                    kind=kind,
                    purpose=str(raw.get("purpose", "")),
                    source=str(raw.get("source", "")),
                    install=str(raw.get("install", "")),
                    status=status,
                    tags=tags,
                    mode=mode,
                    subsector=str(raw.get("subsector", "")),
                    phase=raw.get("phase") if isinstance(raw.get("phase"), int) else None,
                    version=str(raw.get("version", "")),
                    license=str(raw.get("license", "")),
                    trust=str(raw.get("trust", "")),
                    transport=str(raw.get("transport", "")),
                )
            )
    return out


def load_taxonomy(path: Path) -> dict[str, Any]:
    """Declara la taxonomía: dominio → {label, desc, aliases, subsectors}. Es el
    'mapa sin manual' (nombres humanos + alias para que se encuentre como se diga)."""
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: dict[str, Any] = {}
    for sector_id, block in (data.get("sectors") or {}).items():
        block = block or {}
        out[sector_id] = {
            "label": str(block.get("label", sector_id)),
            "desc": str(block.get("desc", "")),
            "aliases": [str(a) for a in (block.get("aliases") or [])],
            "subsectors": {
                sid: {
                    "label": str((sub or {}).get("label", sid)),
                    "aliases": [str(a) for a in ((sub or {}).get("aliases") or [])],
                }
                for sid, sub in (block.get("subsectors") or {}).items()
            },
        }
    return out


_MATURITY = {"instalado": 0, "verificado": 1, "candidato": 2}


def find(
    entries: list[CatalogEntry], taxonomy: dict[str, Any], query: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Buscador 'sin manual': casa `query` contra nombre/propósito/tags/kind y
    contra los ALIAS de sector y subsector (para que se encuentre como cada uno lo
    diga: 'seguridad'→ciberseguridad, 'redteam'→pentesting). Devuelve el camino
    sector/subsector, ordenado madurez-first. Salto directo, sin navegar."""
    q = query.strip().lower()
    if not q:
        return []
    # Sectores/subsectores cuyo id/label/alias casa la query → expanden el match.
    sec_hit, sub_hit = set(), set()
    for sid, sblock in taxonomy.items():
        if q in sid.lower() or q in sblock["label"].lower() or any(q in a.lower() for a in sblock["aliases"]):
            sec_hit.add(sid)
        for subid, sub in sblock["subsectors"].items():
            if q in subid.lower() or q in sub["label"].lower() or any(q in a.lower() for a in sub["aliases"]):
                sub_hit.add((sid, subid))

    hits: list[dict[str, Any]] = []
    for e in entries:
        match = (
            q in e.name.lower()
            or q in e.purpose.lower()
            or q in e.kind.lower()
            or any(q in t.lower() for t in e.tags)
            or e.sector in sec_hit
            or (e.sector, e.subsector) in sub_hit
        )
        if match:
            hits.append({
                "name": e.name, "sector": e.sector, "subsector": e.subsector,
                "kind": e.kind, "status": e.status,
            })
    hits.sort(key=lambda h: (_MATURITY.get(h["status"], 3), h["name"].lower()))
    return hits[:limit]


def in_sector(entries: list[CatalogEntry], sector: str) -> list[CatalogEntry]:
    """Entradas cuyo sector primario o TAGS incluyen `sector` (sector = vista,
    no carpeta exclusiva: un item puede vivir en varios sectores)."""
    return [e for e in entries if e.sector == sector or sector in e.tags]


def sectors(entries: list[CatalogEntry]) -> dict[str, str]:
    """Taxonomía sector_id → label (el eje de clasificación del tronco)."""
    return {e.sector: e.sector_label for e in entries}


def installable(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Solo lo `verificado` se instala (wire-before-claim)."""
    return [e for e in entries if e.status == "verificado"]


def classify(
    name: str, purpose: str, tags: list[str], taxonomy: dict[str, Any],
    *, kind: str | None = None, kind_default: dict[str, str] | None = None,
) -> str:
    """Auto-clasifica a un dominio (sector) por señales, sin manual: primero por TAGS
    que casen el id/alias de un sector o subsector; luego por palabras del nombre/
    propósito contra esos alias. La SEÑAL siempre gana. Sin señal: si el `kind` tiene
    un `kind_default` declarado (política de línea), se usa ese; si no → 'uncategorized'
    (honesto, no fuerza). Token-eficiente: reusa los alias de la taxonomía."""
    hay = " ".join([name, purpose, *tags]).lower()

    # 1) tag exacto = id de sector (señal fuerte, gana directo)
    tagset = {t.lower() for t in tags}
    for sid in taxonomy:
        if sid in tagset:
            return sid

    # 2) SCORE por sector: nº de términos (alias/label de sector+subsectores) que
    #    aparecen como PALABRA COMPLETA en hay. argmax (no first-hit) → evita que un
    #    sector amplio se quede con todo; gana la señal más fuerte.
    def _terms(sblock: dict[str, Any]) -> list[str]:
        out = [sblock["label"], *sblock["aliases"]]
        for sub in sblock["subsectors"].values():
            out += [sub["label"], *sub["aliases"]]
        return [t.lower() for t in out if t]

    best_sid, best_score = "", 0
    for sid, sblock in taxonomy.items():
        terms = set(_terms(sblock)) | {sid.lower()}
        score = sum(1 for t in terms if re.search(rf"\b{re.escape(t)}\b", hay))
        if score > best_score:
            best_sid, best_score = sid, score
    if best_score > 0:
        return best_sid

    # 3) sin señal: fallback por línea (política declarada), si la hay
    if kind and kind_default and kind in kind_default:
        return kind_default[kind]
    return "uncategorized"


def classify_subsector(
    name: str, purpose: str, tags: list[str], sector: str, taxonomy: dict[str, Any]
) -> str:
    """Dentro de un sector ya elegido, asigna subsector por alias/label de subsector
    en nombre/propósito/tags. Sin señal o sector sin subsectores → '' (honesto)."""
    subs = (taxonomy.get(sector) or {}).get("subsectors", {})
    if not subs:
        return ""
    hay = " ".join([name, purpose, *tags]).lower()
    for subid, sub in subs.items():
        terms = [subid, sub["label"], *sub["aliases"]]
        if any(t and t.lower() in hay for t in terms):
            return str(subid)
    return ""


def by_kind(entries: list[CatalogEntry]) -> dict[str, int]:
    """Cuenta por kind = tamaño de cada 'línea' del catálogo."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return counts


def of_kind(entries: list[CatalogEntry], kind: str) -> list[CatalogEntry]:
    """Una sola línea: todas las entradas de un kind (across sectores)."""
    return [e for e in entries if e.kind == kind]


def by_status(entries: list[CatalogEntry]) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in _STATES}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    return counts
