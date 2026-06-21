#!/usr/bin/env python3
"""Clasifica TODO lo sembrado (todas las líneas) a dominios → mcp_catalog_classified.yaml.

Auto-clasificador (atlas.mcp.catalog.classify): asigna sector por tags/alias, sin
manual. Lee la taxonomía del catálogo curado + todos los `docs/design/**/*seeded*.yaml`,
clasifica cada candidato, y escribe un catálogo clasificado (máquina-generado) +
reporta cobertura por dominio. Todo sigue `candidato` (clasificar ≠ verificar).

    python3 scripts/mcp_classify_seeded.py
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.catalog import classify, load_catalog, load_taxonomy  # noqa: E402

_CURATED = ROOT / "docs" / "design" / "mcp_catalog.yaml"
_OUT = ROOT / "docs" / "design" / "mcp_catalog_classified.yaml"


def _seeded_files() -> list[Path]:
    d = ROOT / "docs" / "design"
    return sorted(set(d.glob("*seeded*.yaml")) | set((d / "seeded").glob("*.yaml")))


def main() -> int:
    tax = load_taxonomy(_CURATED)
    by_sector: dict[str, list[dict]] = {}
    line_counts: Counter[str] = Counter()
    for f in _seeded_files():
        for e in load_catalog(f):
            sector = classify(e.name, e.purpose, e.tags, tax)
            line_counts[e.kind] += 1
            by_sector.setdefault(sector, []).append({
                "name": e.name, "kind": e.kind, "subsector": e.subsector,
                "mode": e.mode, "source": e.source, "install": e.install,
                "status": e.status, "tags": e.tags,
            })

    sectors_doc = {}
    for sid, entries in sorted(by_sector.items()):
        label = tax.get(sid, {}).get("label", sid)
        sectors_doc[sid] = {"label": label, "entries": entries}
    doc = {
        "_generated": {
            "by": "scripts/mcp_classify_seeded.py",
            "at": datetime.now(timezone.utc).isoformat(),
            "note": "MÁQUINA-GENERADO. Clasificación automática por alias; todo candidato.",
        },
        "sectors": sectors_doc,
    }
    _OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    total = sum(len(v) for v in by_sector.values())
    print(f"clasificados {total} candidatos → {_OUT.relative_to(ROOT)}\n")
    print("Cobertura por DOMINIO:")
    for sid in list(tax) + ["uncategorized"]:
        n = len(by_sector.get(sid, []))
        bar = "█" * min(40, n // 5)
        print(f"  {sid:22s} {n:4d} {bar}")
    print("\nPor LÍNEA (kind):", dict(line_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
