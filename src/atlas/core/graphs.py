"""Grafo de imports bitemporal sobre Kuzu (backlog: kuzu_bitemporal_schema, slice 2).

Slice 1 (`scripts/code_graph.py`) analiza el working tree actual. Slice 2
congela un snapshot del grafo de imports POR COMMIT — vía `git ls-tree` /
`git show`, sin checkout ni tocar el working tree — y lo persiste en Kuzu
con identidad `path@commit_sha`, para poder preguntar por linaje temporal:
qué cambió entre dos commits, quién se ve afectado en cascada, y qué
ficheros mutan más.

Reimplementa (no importa) el resolver de imports de `scripts/code_graph.py`:
aquél lee el filesystem vía `Path.rglob`, éste lee blobs de git — misma
heurística de resolución (`from MODULO import NOMBRE` → arista a submódulo
si `MODULO.NOMBRE` es un módulo real, a símbolo si no), fuente de bytes
distinta. `scripts/` no es parte del paquete instalado (no tiene
`__init__.py`); importar desde ahí violaría la frontera de distribución.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import kuzu

__all__ = [
    "list_files_at_commit",
    "read_file_at_commit",
    "build_import_graph_at_commit",
    "build_bitemporal_graph",
    "load_bitemporal_into_kuzu",
    "QUERIES",
]


class _Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...
    @property
    def dim(self) -> int: ...


def list_files_at_commit(repo_root: Path, commit_sha: str, subdir: str = "src/atlas") -> list[str]:
    """Rutas .py bajo `subdir` tal como existían en `commit_sha` (sin checkout)."""
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit_sha, "--", subdir],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line
        for line in out.stdout.splitlines()
        if line.endswith(".py") and not line.endswith("__init__.py")
    ]


def read_file_at_commit(repo_root: Path, commit_sha: str, rel_path: str) -> bytes:
    """Contenido del blob en `commit_sha` (git show, sin tocar el working tree)."""
    out = subprocess.run(
        ["git", "show", f"{commit_sha}:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return out.stdout


def _module_name(rel_path: str, subdir: str) -> str:
    tail = rel_path[len(subdir) :].lstrip("/")
    return "atlas." + tail[:-3].replace("/", ".")


def build_import_graph_at_commit(
    repo_root: Path, commit_sha: str, subdir: str = "src/atlas"
) -> dict[str, dict[str, Any]]:
    """Grafo de imports + hash de contenido, congelado en `commit_sha`.

    Devuelve ``{module_name: {"hash": sha256hex, "imports": set[str]}}``.
    """
    rel_paths = list_files_at_commit(repo_root, commit_sha, subdir)
    contents: dict[str, bytes] = {}
    trees: dict[str, ast.Module] = {}
    for rel_path in rel_paths:
        module_name = _module_name(rel_path, subdir)
        content = read_file_at_commit(repo_root, commit_sha, rel_path)
        contents[module_name] = content
        try:
            trees[module_name] = ast.parse(content.decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

    real_modules = set(trees.keys())
    graph: dict[str, dict[str, Any]] = {
        m: {"hash": hashlib.sha256(contents[m]).hexdigest(), "imports": set()} for m in contents
    }

    for module_name, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("atlas."):
                        graph[module_name]["imports"].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    parent_parts = module_name.split(".")[:-1]
                    for _ in range(node.level - 1):
                        if parent_parts:
                            parent_parts.pop()
                    base = ".".join(parent_parts + [node.module]) if node.module else ".".join(parent_parts)
                else:
                    base = node.module or ""

                if not base or (base != "atlas" and not base.startswith("atlas.")):
                    continue

                added_submodule = False
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    if candidate in real_modules:
                        graph[module_name]["imports"].add(candidate)
                        added_submodule = True
                if not added_submodule:
                    graph[module_name]["imports"].add(base)

    return graph


def build_bitemporal_graph(repo_root: Path, commit_shas: list[str]) -> dict[str, Any]:
    """Snapshots por-commit + diffs consecutivos (added/removed/modified).

    Devuelve ``{"snapshots": {sha: graph}, "diffs": [{"from", "to", "added", "removed", "modified"}]}``.
    """
    snapshots = {sha: build_import_graph_at_commit(repo_root, sha) for sha in commit_shas}
    diffs: list[dict[str, Any]] = []
    for prev_sha, cur_sha in zip(commit_shas, commit_shas[1:]):
        prev, cur = snapshots[prev_sha], snapshots[cur_sha]
        prev_mods, cur_mods = set(prev), set(cur)
        diffs.append(
            {
                "from": prev_sha,
                "to": cur_sha,
                "added": sorted(cur_mods - prev_mods),
                "removed": sorted(prev_mods - cur_mods),
                "modified": sorted(m for m in (prev_mods & cur_mods) if prev[m]["hash"] != cur[m]["hash"]),
            }
        )
    return {"snapshots": snapshots, "diffs": diffs}


_SCHEMA = (
    "CREATE NODE TABLE IF NOT EXISTS FileVersion("
    "id STRING, path STRING, hash STRING, commit_sha STRING, "
    "ingested_at TIMESTAMP, embedding DOUBLE[], PRIMARY KEY(id))",
    "CREATE REL TABLE IF NOT EXISTS IMPORTS(FROM FileVersion TO FileVersion, commit_sha STRING)",
    "CREATE REL TABLE IF NOT EXISTS EVOLVES_TO(FROM FileVersion TO FileVersion, change_type STRING)",
)


def load_bitemporal_into_kuzu(
    repo_root: Path,
    db_path: Path,
    commit_shas: list[str],
    *,
    embedder: _Embedder | None = None,
    max_db_size: int = 1 << 30,
) -> dict[str, Any]:
    """Congela `commit_shas` en Kuzu con identidad `path@commit_sha`.

    Idempotente (MERGE por `id`): reingerir los mismos commits no duplica
    nodos ni aristas. El embedding es del texto "`path` imports: `imports`"
    (no del contenido del fichero) — barato y suficiente para agrupar
    módulos con vecindarios de imports parecidos; `embedder=None` usa
    `StubEmbedder` (hash, sin red) para no forzar una dependencia pesada
    en el hot path de ingesta.
    """
    if embedder is None:
        from atlas.memory.embeddings import StubEmbedder

        embedder = StubEmbedder(dim=64)

    bg = build_bitemporal_graph(repo_root, commit_shas)
    snapshots = bg["snapshots"]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(db_path), max_db_size=max_db_size)
    conn = kuzu.Connection(db)
    try:
        for ddl in _SCHEMA:
            conn.execute(ddl)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        nodes = 0
        for sha, graph in snapshots.items():
            for module, info in graph.items():
                text = f"{module} imports: {','.join(sorted(info['imports']))}"
                conn.execute(
                    "MERGE (n:FileVersion {id: $id}) "
                    "SET n.path = $path, n.hash = $hash, n.commit_sha = $sha, "
                    "n.ingested_at = $ts, n.embedding = $emb",
                    {
                        "id": f"{module}@{sha}",
                        "path": module,
                        "hash": info["hash"],
                        "sha": sha,
                        "ts": now,
                        "emb": embedder.embed(text),
                    },
                )
                nodes += 1

        edges = 0
        for sha, graph in snapshots.items():
            for module, info in graph.items():
                for imported in info["imports"]:
                    if imported not in graph:
                        continue  # arista solo dentro del snapshot congelado
                    conn.execute(
                        "MATCH (a:FileVersion {id: $a}), (b:FileVersion {id: $b}) "
                        "MERGE (a)-[:IMPORTS {commit_sha: $sha}]->(b)",
                        {"a": f"{module}@{sha}", "b": f"{imported}@{sha}", "sha": sha},
                    )
                    edges += 1

        evolves = 0
        for diff in bg["diffs"]:
            prev_sha, cur_sha = diff["from"], diff["to"]
            prev, cur = snapshots[prev_sha], snapshots[cur_sha]
            for module in set(prev) & set(cur):
                change_type = "modified" if prev[module]["hash"] != cur[module]["hash"] else "unchanged"
                conn.execute(
                    "MATCH (a:FileVersion {id: $a}), (b:FileVersion {id: $b}) "
                    "MERGE (a)-[:EVOLVES_TO {change_type: $ct}]->(b)",
                    {"a": f"{module}@{prev_sha}", "b": f"{module}@{cur_sha}", "ct": change_type},
                )
                evolves += 1

        return {"nodes": nodes, "imports_edges": edges, "evolves_edges": evolves, "diffs": bg["diffs"]}
    finally:
        conn.close()
        db.close()


# ---------------------------------------------------------------------------
# 5 queries complejas: diffs, impacto, linaje temporal.
# ---------------------------------------------------------------------------
QUERIES: dict[str, str] = {
    # 1. Qué módulos cambiaron de contenido entre dos commits.
    "diff_modified": (
        "MATCH (a:FileVersion)-[e:EVOLVES_TO]->(b:FileVersion) "
        "WHERE e.change_type = 'modified' AND a.commit_sha = $from_sha AND b.commit_sha = $to_sha "
        "RETURN a.path AS path, a.hash AS old_hash, b.hash AS new_hash"
    ),
    # 2. Linaje temporal completo de un fichero: su hash en cada commit ingerido.
    "temporal_lineage": (
        "MATCH (v:FileVersion) WHERE v.path = $path "
        "RETURN v.commit_sha AS commit_sha, v.hash AS hash, v.ingested_at AS ingested_at "
        "ORDER BY v.ingested_at"
    ),
    # 3. Impacto directo: quién importa este módulo en un commit dado.
    "direct_importers": (
        "MATCH (importer:FileVersion)-[i:IMPORTS]->(target:FileVersion) "
        "WHERE target.path = $path AND target.commit_sha = $sha "
        "RETURN importer.path AS importer"
    ),
    # 4. Radio de impacto transitivo (hasta 4 saltos) dentro de un mismo commit.
    "blast_radius": (
        "MATCH (importer:FileVersion)-[:IMPORTS*1..4]->(target:FileVersion) "
        "WHERE target.path = $path AND target.commit_sha = $sha AND importer.commit_sha = $sha "
        "RETURN DISTINCT importer.path AS importer"
    ),
    # 5. Ficheros que más mutan a través de los commits ingeridos (churn).
    "most_changed_files": (
        "MATCH (a:FileVersion)-[e:EVOLVES_TO]->(b:FileVersion) "
        "WHERE e.change_type = 'modified' "
        "RETURN a.path AS path, count(*) AS times_modified "
        "ORDER BY times_modified DESC LIMIT 10"
    ),
}
