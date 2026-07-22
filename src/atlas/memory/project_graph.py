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

from atlas.core.git_env import clean_git_env
from atlas.core.graphs import load_bitemporal_into_kuzu

__all__ = [
    "DEFAULT_GRAPH_DB",
    "build_project_graph",
    "graph_freshness",
    "graph_head_sha",
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


def graph_head_sha(repo_root: Path | None) -> str:
    """HEAD del checkout, o ``""`` si no hay repo/git utilizable (fail-honesto)."""
    if repo_root is None:
        return ""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _source_tree_dirty(repo_root: Path | None) -> bool | None:
    """Si los inputs commiteados del grafo (``src/atlas``) difieren del árbol vivo.

    El grafo se construye desde snapshots ``git show``: coincidir con HEAD no
    basta mientras hay ediciones sin commitear — no están en Kuzu. ``None``
    significa que el propio check no es fiable.
    """
    if repo_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", "src/atlas"],
            cwd=repo_root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def graph_freshness(
    db_path: Path = DEFAULT_GRAPH_DB,
    *,
    repo_root: Path | None = None,
    server_started_head_sha: str | None = None,
) -> dict[str, Any]:
    """Frescura del grafo vs el checkout — read-only, nunca lanza por diseño.

    Fuente única del vocabulario ``FRESH/DIRTY/STALE/SERVER_STALE/EMPTY/
    UNKNOWN/NO_DB/UNAVAILABLE``: la consumen el graph_server MCP y
    ``atlas reality``. ``server_started_head_sha=None`` = sin proceso server en
    juego (reality); ``""`` = server presente pero sin sha al arrancar.
    """
    path = Path(db_path).expanduser()
    state: dict[str, Any] = {
        "db_path": str(path),
        "graph_commit_sha": "",
        "head_sha": "",
        "source_tree_dirty": None,
    }
    if not path.exists():
        return {**state, "status": "NO_DB", "reason": f"graph db not found: {path}"}
    try:
        import kuzu
    except Exception as exc:  # noqa: BLE001
        return {**state, "status": "UNAVAILABLE", "reason": f"kuzu unavailable: {type(exc).__name__}"}
    graph_sha = ""
    try:
        db = kuzu.Database(str(path), read_only=True)
        try:
            conn = kuzu.Connection(db)
            try:
                result: Any = conn.execute(
                    "MATCH (v:FileVersion) "
                    "RETURN v.commit_sha, max(v.ingested_at) AS t ORDER BY t DESC LIMIT 1"
                )
                if result.has_next():
                    graph_sha = str(result.get_next()[0])
            except Exception:  # noqa: BLE001 — tabla ausente = nada ingerido aún
                graph_sha = ""
            finally:
                conn.close()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — p.ej. write-lock de una regeneración en curso
        return {**state, "status": "UNAVAILABLE", "reason": type(exc).__name__}

    head_sha = graph_head_sha(repo_root)
    source_dirty = _source_tree_dirty(repo_root)
    state.update(graph_commit_sha=graph_sha, head_sha=head_sha, source_tree_dirty=source_dirty)
    if not graph_sha:
        return {**state, "status": "EMPTY", "reason": "no FileVersion rows ingested"}
    if not head_sha or source_dirty is None:
        return {**state, "status": "UNKNOWN", "reason": "git state unavailable"}
    if graph_sha != head_sha:
        return {**state, "status": "STALE", "reason": "graph behind HEAD"}
    if source_dirty:
        return {**state, "status": "DIRTY", "reason": "working tree differs from ingested HEAD"}
    if server_started_head_sha is not None:
        if not server_started_head_sha:
            return {**state, "status": "UNKNOWN", "reason": "server start sha unavailable"}
        if server_started_head_sha != head_sha:
            return {**state, "status": "SERVER_STALE", "reason": "server process predates HEAD"}
    return {**state, "status": "FRESH", "reason": "graph matches HEAD on a clean tree"}


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
