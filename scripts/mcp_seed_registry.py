#!/usr/bin/env python3
"""Siembra candidatos del registro oficial MCP → docs/design/mcp_catalog_seeded.yaml.

Fichero MÁQUINA-GENERADO, separado del catálogo curado: todo entra `candidato` y
`uncategorized` con procedencia. Verificar (prove-it) y clasificar por sector son
pasos posteriores y explícitos (no kitchen-sink, wire-before-claim).

    python3 scripts/mcp_seed_registry.py            # red real (registry allowlisted)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.registry_seed import RegistrySource, reseed_candidates  # noqa: E402

_OUT = ROOT / "docs" / "design" / "mcp_catalog_seeded.yaml"
_SOURCE_URL = "https://registry.modelcontextprotocol.io/v0/servers"


def main() -> int:
    """Wrapper delgado sobre ``reseed_candidates()`` (A.1, ADR-076) -- la
    lógica de paginación+dedup vive en ``atlas.mcp.registry_seed`` para que un
    tick del scheduler (A.2) la reuse sin pasar por este script. El CLI manual
    sigue funcionando igual: red real, mismo fichero de salida."""
    try:
        result = reseed_candidates(source=RegistrySource(limit=100))
    except RuntimeError as exc:
        print(str(exc))
        return 1
    cands = result["candidates"]
    pages_ok = result["pages_fetched"]
    doc = {
        "_generated": {
            "by": "scripts/mcp_seed_registry.py",
            "at": datetime.now(timezone.utc).isoformat(),
            "source": _SOURCE_URL,
            "note": "MÁQUINA-GENERADO. Todo candidato/uncategorized. Triar + prove-it antes de usar.",
            "pages_fetched": pages_ok,
        },
        "sectors": {
            "uncategorized": {
                "label": "Sin clasificar (sembrado del registro oficial)",
                "entries": cands,
            }
        },
    }
    _OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"sembrados {len(cands)} candidatos ({pages_ok} paginas) -> {_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
