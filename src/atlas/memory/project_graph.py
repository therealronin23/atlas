"""Grafo vivo del proyecto en Kuzu — "el grafo ES el presente" (directiva 2026-07-09).

Los documentos son el pasado y el futuro; el estado estructural REAL del código
se consulta aquí, no leyendo .md. Una sola BD Kuzu estable reúne:

- El grafo de imports bitemporal (``atlas.core.graphs``): FileVersion + IMPORTS +
  EVOLVES_TO sobre los últimos N commits — quién importa qué, blast radius,
  linaje temporal, churn.
- Opcionalmente el vault Obsidian del proyecto (``atlas.memory.obsidian_to_kuzu``):
  ObsidianNote + LINKS_TO — el conocimiento en notas, mismo lenguaje de consulta.

Regenerable en cualquier momento (idempotente: todo MERGE); pensado para
correrse tras cada lote ColdUpdate aprobado o como extra_cycle del scheduler.
El consumidor es ``atlas.mcp.graph_server`` (tools MCP de consulta) — cualquier
IA conectada al tronco entiende Atlas sin quemar tokens en documentos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from atlas.core.graphs import load_bitemporal_into_kuzu

__all__ = ["DEFAULT_GRAPH_DB", "build_project_graph", "recent_commits"]

# BD estable bajo el home de Atlas (junto al Kuzu del vector store, fichero aparte
# para poder recrearla sin tocar memoria de producción).
DEFAULT_GRAPH_DB = Path.home() / "atlas" / "memory" / "kuzu" / "project_graph.kuzu"


def recent_commits(repo_root: Path, n: int = 10) -> list[str]:
    """Últimos ``n`` commits de la rama actual, en orden cronológico (viejo→nuevo),
    que es el orden que espera la capa bitemporal para calcular EVOLVES_TO."""
    out = subprocess.run(
        ["git", "log", f"-{n}", "--format=%H", "--reverse"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def build_project_graph(
    repo_root: Path,
    db_path: Path = DEFAULT_GRAPH_DB,
    *,
    commits: int = 10,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """(Re)genera el grafo del proyecto. Idempotente; devuelve métricas.

    ``vault_root`` opcional: si se pasa y existe, carga también el vault
    Obsidian en la misma BD (tablas independientes, sin colisión de esquema).
    """
    shas = recent_commits(repo_root, commits)
    metrics: dict[str, Any] = {"commits": shas}
    metrics["bitemporal"] = load_bitemporal_into_kuzu(repo_root, db_path, shas)

    if vault_root is not None and vault_root.is_dir():
        from atlas.memory.obsidian_to_kuzu import load_vault_into_kuzu

        metrics["vault"] = load_vault_into_kuzu(vault_root, db_path)

    return metrics


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_GRAPH_DB)
    parser.add_argument("--commits", type=int, default=10)
    parser.add_argument("--vault", type=Path, default=None)
    args = parser.parse_args()
    print(
        json.dumps(
            build_project_graph(
                args.repo_root, args.db, commits=args.commits, vault_root=args.vault
            ),
            indent=2,
            default=str,
        )
    )
