#!/usr/bin/env python3
"""Instalador del catálogo MCP (línea B/C) — read-only por defecto.

Lee docs/design/mcp_catalog.yaml (estructurado, clasificado por sector/necesidad),
reporta por sector y estado, y lista lo INSTALABLE (solo `verificado`; nunca
candidatos — wire-before-claim). La EJECUCIÓN de instalación se añade cuando haya
entradas verificadas (hoy 0, y eso es lo correcto).

    python3 scripts/mcp_install.py

El agente decide QUÉ marcar `verificado` (lo que se gana su sitio tras prove-it);
este script ejecuta la parte mecánica.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from atlas.mcp.catalog import (  # noqa: E402
    CatalogEntry,
    by_status,
    load_catalog,
    sectors,
)
from atlas.mcp.trunk_manifest import native_roots, tool_overhead  # noqa: E402


def main() -> int:
    path = ROOT / "docs" / "design" / "mcp_catalog.yaml"
    entries = load_catalog(path)
    counts = by_status(entries)

    print("# Instalador catálogo MCP (read-only)")
    print(f"\nCatálogo: {path.relative_to(ROOT)}  ({len(entries)} entradas)")
    for state in ("verificado", "candidato", "instalado"):
        print(f"  {state}: {counts.get(state, 0)}")

    print("\n## Clasificación por sector/necesidad")
    grouped: dict[str, list[CatalogEntry]] = defaultdict(list)
    for e in entries:
        grouped[e.sector].append(e)
    tax = sectors(entries)
    for sec, label in tax.items():
        marks = " ".join(f"{e.name}[{e.status[0]}]" for e in grouped[sec])
        print(f"  - {sec} ({label}): {marks}")

    from atlas.mcp.installer import plan_install, vet_action  # noqa: E402

    plan = plan_install(entries)
    print("\n## Plan de instalación (estado=verificado, por mode)")
    if not plan:
        print("  (nada — wire-before-claim: marca `verificado` lo comprobado con prove-it)")
    else:
        for a in plan:
            veto = vet_action(a)
            flag = f" ⛔ VETADO: {veto}" if veto else ""
            cmd = " ".join(a.command) if a.command else "—"
            print(f"  - {a.name}: {a.action} ({a.mode}) [{cmd}]{flag}")

    print("\n## Tronco nativo (vivo)")
    for r in native_roots():
        print(f"  - {r.name}: {', '.join(r.tools) or '(solo recursos)'}")
    print(f"\nOverhead de superficie nativa: {tool_overhead()} tools (anti-kitchen-sink).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
