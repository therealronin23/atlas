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

import os
import subprocess
from pathlib import Path
from typing import Any

from atlas.core.graphs import load_bitemporal_into_kuzu

__all__ = [
    "DEFAULT_GRAPH_DB",
    "build_project_graph",
    "recent_commits",
    "resolve_graph_embedder",
]

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
    embedder: Any | None = None,
) -> dict[str, Any]:
    """(Re)genera el grafo del proyecto. Idempotente; devuelve métricas.

    ``vault_root`` opcional: si se pasa y existe, carga también el vault
    Obsidian en la misma BD (tablas independientes, sin colisión de esquema).

    ``embedder`` opcional (keyword-only): se propaga tal cual a
    ``load_bitemporal_into_kuzu``. Default ``None`` mantiene el comportamiento
    EXACTO de antes — ``StubEmbedder(dim=64)`` — para no romper a nadie que ya
    llame a esta función sin argumento. Quién decide un embedder distinto en
    producción (vía ``resolve_graph_embedder`` + env) es responsabilidad del
    llamador (el tick), no de este default.
    """
    shas = recent_commits(repo_root, commits)
    metrics: dict[str, Any] = {"commits": shas}
    metrics["bitemporal"] = load_bitemporal_into_kuzu(repo_root, db_path, shas, embedder=embedder)

    if vault_root is not None and vault_root.is_dir():
        from atlas.memory.obsidian_to_kuzu import load_vault_into_kuzu

        metrics["vault"] = load_vault_into_kuzu(vault_root, db_path)

    return metrics


def resolve_graph_embedder() -> Any | None:
    """Traduce ``ATLAS_GRAPH_EMBEDDER`` a un embedder concreto (o ``None`` = stub).

    - ``"fastembed"`` → ``atlas.memory.embeddings.default_embedder()`` (import
      perezoso: no paga el coste de cargar el modelo ONNX si nadie pide
      fastembed). Coste real: ~470MB de RSS por PROCESO la primera vez que se
      instancia — pero `FastEmbedEmbedder._MODEL_CACHE` ya lo cachea a nivel de
      proceso, así que llamadas repetidas dentro del mismo proceso (p.ej. el
      tick reingeriendo en cada ciclo) no vuelven a pagarlo. Además, cambiar de
      embedder cambia la dimensión del vector: reingerir con `fastembed` sobre
      una BD que ya tenía nodos con `embedding` de otra dim los actualiza in
      situ vía MERGE (no falla, pero mezcla dims si la migración queda a
      medias — no hay DDL de por medio porque `FileVersion.embedding` es
      `DOUBLE[]` de longitud variable).
    - ``"stub"`` o vacío/sin definir → ``None`` (deja que
      ``load_bitemporal_into_kuzu``/``build_project_graph`` usen su default
      actual, ``StubEmbedder(dim=64)``).
    """
    choice = os.environ.get("ATLAS_GRAPH_EMBEDDER", "").strip().lower()
    if choice == "fastembed":
        from atlas.memory.embeddings import default_embedder

        return default_embedder()
    return None


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_GRAPH_DB)
    parser.add_argument("--commits", type=int, default=10)
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument(
        "--embedder",
        choices=["stub", "fastembed"],
        default="stub",
        help="Embedder para los vectores de FileVersion (default: stub, sin red).",
    )
    args = parser.parse_args()
    os.environ["ATLAS_GRAPH_EMBEDDER"] = args.embedder
    print(
        json.dumps(
            build_project_graph(
                args.repo_root,
                args.db,
                commits=args.commits,
                vault_root=args.vault,
                embedder=resolve_graph_embedder(),
            ),
            indent=2,
            default=str,
        )
    )
