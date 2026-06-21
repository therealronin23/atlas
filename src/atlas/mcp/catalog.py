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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_STATES = {"candidato", "verificado", "instalado"}
_KINDS = {"skill", "mcp", "api", "tool"}


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
                )
            )
    return out


def sectors(entries: list[CatalogEntry]) -> dict[str, str]:
    """Taxonomía sector_id → label (el eje de clasificación del tronco)."""
    return {e.sector: e.sector_label for e in entries}


def installable(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Solo lo `verificado` se instala (wire-before-claim)."""
    return [e for e in entries if e.status == "verificado"]


def by_status(entries: list[CatalogEntry]) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in _STATES}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    return counts
