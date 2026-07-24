#!/usr/bin/env python3
"""Siembra candidatos del registro oficial MCP → docs/design/mcp_catalog_seeded.yaml.

Fichero MÁQUINA-GENERADO, separado del catálogo curado: todo entra `candidato` y
`uncategorized` con procedencia. Verificar (prove-it) y clasificar por sector son
pasos posteriores y explícitos (no kitchen-sink, wire-before-claim).

    python3 scripts/mcp_seed_registry.py            # red real (registry allowlisted)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from atlas.mcp.registry_seed import RegistrySource, reseed_candidates, write_seeded_catalog  # noqa: E402

_OUT = ROOT / "docs" / "design" / "mcp_catalog_seeded.yaml"
_SOURCE_URL = "https://registry.modelcontextprotocol.io/v0/servers"


def main() -> int:
    """Wrapper delgado sobre ``reseed_candidates()``/``write_seeded_catalog()``
    (A.1/A.2, ADR-076) -- la lógica de paginación+dedup+escritura vive en
    ``atlas.mcp.registry_seed`` para que un tick del scheduler (A.2) la reuse
    sin pasar por este script. El CLI manual sigue funcionando igual: red
    real, mismo fichero de salida."""
    try:
        result = reseed_candidates(source=RegistrySource(limit=100))
    except RuntimeError as exc:
        print(str(exc))
        return 1
    write_seeded_catalog(_OUT, result, source_url=_SOURCE_URL, generated_by="scripts/mcp_seed_registry.py")
    print(f"sembrados {len(result['candidates'])} candidatos ({result['pages_fetched']} paginas) -> {_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
