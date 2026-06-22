"""Script de instalación del trunk MCP de Atlas.

Escribe (o fusiona) la entrada "atlas-trunk" en ~/atlas/mcp_servers.json.
Idempotente: conserva cualquier otro server ya presente; solo añade/actualiza
la entrada "atlas-trunk".

Uso:
    python scripts/atlas_install_trunk.py [--python /ruta/a/python]

NO ejecuta nada de red; NO arranca el servidor.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Añadir src/ al path cuando se ejecuta directamente (fuera de un entorno
# instalado).
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from atlas.mcp.trunk_manifest import atlas_mcp_config  # noqa: E402


def _repo_root() -> Path:
    """Raíz del repositorio (directorio que contiene este script/..)."""
    return _HERE.parent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Instala la config del trunk MCP de Atlas.")
    parser.add_argument(
        "--python",
        default=None,
        help="Ejecutable Python para el trunk. Por defecto: sys.executable del entorno actual.",
    )
    args = parser.parse_args(argv)

    save_dir = Path.home() / "atlas-mcp"
    repo_root = _repo_root()
    target = Path.home() / "atlas" / "mcp_servers.json"

    # Generar la nueva entrada
    new_entries = atlas_mcp_config(save_dir=save_dir, repo_root=repo_root, python=args.python)
    new_by_name: dict[str, dict[str, object]] = {str(e["name"]): e for e in new_entries}

    # Leer config existente si la hay
    existing: list[dict[str, object]] = []
    if target.exists():
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            existing = [e for e in raw if isinstance(e, dict)]

    # Fusionar: conservar servers no-trunk, añadir/actualizar los nuevos
    merged: list[dict[str, object]] = [e for e in existing if e.get("name") not in new_by_name]
    merged.extend(new_by_name.values())

    # Asegurar que el directorio existe
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Escrito: {target}")
    print(json.dumps(merged, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
