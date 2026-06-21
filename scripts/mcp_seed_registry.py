#!/usr/bin/env python3
"""Siembra candidatos del registro oficial MCP → docs/design/mcp_catalog_seeded.yaml.

Fichero MÁQUINA-GENERADO, separado del catálogo curado: todo entra `candidato` y
`uncategorized` con procedencia. Verificar (prove-it) y clasificar por sector son
pasos posteriores y explícitos (no kitchen-sink, wire-before-claim).

    python3 scripts/mcp_seed_registry.py            # red real (registry allowlisted)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.registry_seed import RegistrySource, registry_to_candidates  # noqa: E402

_OUT = ROOT / "docs" / "design" / "mcp_catalog_seeded.yaml"
_SOURCE_URL = "https://registry.modelcontextprotocol.io/v0/servers"


def main() -> int:
    rec = RegistrySource(limit=100).fetch(None)[0]
    if rec.status != 200:
        print(f"registro no accesible: status={rec.status} ({rec.payload[:120]})")
        return 1
    cands = registry_to_candidates(json.loads(rec.payload), source_url=_SOURCE_URL)
    doc = {
        "_generated": {
            "by": "scripts/mcp_seed_registry.py",
            "at": datetime.now(timezone.utc).isoformat(),
            "source": _SOURCE_URL,
            "note": "MÁQUINA-GENERADO. Todo candidato/uncategorized. Triar + prove-it antes de usar.",
        },
        "sectors": {
            "uncategorized": {
                "label": "Sin clasificar (sembrado del registro oficial)",
                "entries": cands,
            }
        },
    }
    _OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"sembrados {len(cands)} candidatos → {_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
