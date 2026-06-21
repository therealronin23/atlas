"""
Atlas Core — Installer del catálogo MCP (MCP trunk, F4).

Lee `docs/design/mcp_catalog.md` (tablas markdown con columna Estado) y respeta
`wire-before-claim`: SOLO es instalable lo marcado `verificado` — nunca un
`candidato` (sin verificar) ni un `instalado` (ya está). El agente decide QUÉ
(marca `verificado` lo que se gana su sitio); este código ejecuta la parte
mecánica (`feedback-least-effort-automation`).

Honesto: el catálogo es un volcado UNVERIFICADO; por eso el estado por defecto es
`candidato` y el instalador no instala nada hasta que un humano/agente verifica.

Diseño: docs/design/mcp_trunk_portable.md (F4) + docs/design/mcp_catalog.md.
"""

from __future__ import annotations

from dataclasses import dataclass

_STATES = {"candidato", "verificado", "instalado"}


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    status: str


def parse_catalog(markdown: str) -> list[CatalogEntry]:
    """Extrae (nombre, estado) de las filas de tabla del catálogo. Una fila
    cuenta si su última celda es un estado conocido; el nombre es la 1ª celda.
    Ignora cabeceras, separadores y prosa."""
    entries: list[CatalogEntry] = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        status = cells[-1].lower()
        if status not in _STATES:
            continue  # cabecera ("Estado") o separador
        name = cells[0]
        if not name or set(name) <= {"-", ":"}:
            continue
        entries.append(CatalogEntry(name=name, status=status))
    return entries


def installable(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Solo lo `verificado` se instala (wire-before-claim)."""
    return [e for e in entries if e.status == "verificado"]


def summary(entries: list[CatalogEntry]) -> dict[str, int]:
    """Conteo por estado (para el reporte del instalador)."""
    counts: dict[str, int] = {s: 0 for s in _STATES}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    return counts
