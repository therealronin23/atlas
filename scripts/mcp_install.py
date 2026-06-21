#!/usr/bin/env python3
"""Instalador del catálogo MCP (MCP trunk F4) — read-only por defecto.

Lee docs/design/mcp_catalog.md, reporta por estado y lista lo INSTALABLE (solo
`verificado`; nunca candidatos — wire-before-claim). NO instala nada todavía:
la resolución a repo/comando + descarga se añade cuando haya entradas verificadas.

    python3 scripts/mcp_install.py

El agente decide QUÉ marcar `verificado` (lo que se gana su sitio); este script
ejecuta la parte mecánica. Mientras el catálogo siga todo en `candidato`, el
reporte dirá "nada instalable" — y eso es lo correcto.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from atlas.mcp.installer import installable, parse_catalog, summary  # noqa: E402
from atlas.mcp.trunk_manifest import native_roots, tool_overhead  # noqa: E402


def main() -> int:
    catalog_path = ROOT / "docs" / "design" / "mcp_catalog.md"
    entries = parse_catalog(catalog_path.read_text(encoding="utf-8"))
    counts = summary(entries)

    print("# Instalador catálogo MCP (read-only)")
    print(f"\nCatálogo: {catalog_path.relative_to(ROOT)}  ({len(entries)} entradas)")
    for state in ("verificado", "candidato", "instalado"):
        print(f"  {state}: {counts.get(state, 0)}")

    to_install = installable(entries)
    print("\n## Instalable (estado=verificado)")
    if not to_install:
        print("  (nada — wire-before-claim: marca `verificado` lo que se gana su sitio)")
    else:
        for e in to_install:
            print(f"  - {e.name}")

    print("\n## Tronco nativo (una conexión)")
    for r in native_roots():
        surface = ", ".join(r.tools) or "(solo recursos)"
        print(f"  - {r.name}: {surface}")
    print(f"\nOverhead de superficie: {tool_overhead()} tools (anti-kitchen-sink).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
