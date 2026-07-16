"""Shell FastMCP del grafo del proyecto — consultar Atlas sin leer documentos.

Sirve las queries del grafo vivo (``atlas.memory.project_graph``) por MCP:
quién importa un módulo, radio de impacto transitivo, linaje temporal de un
fichero, churn, vecindario de notas Obsidian, y quién llama/a quién llama un
símbolo del call-graph (``atlas.memory.callgraph_to_kuzu``). El objetivo es
que cualquier IA conectada al tronco entienda la estructura REAL de Atlas con una query
barata en vez de quemar tokens leyendo .md (que son pasado/futuro, no presente).

Mismo patrón de capa-transporte que ``memory_server``/``knowledge_server``:
SDK `mcp` opcional, import diferido, sin lógica de dominio aquí.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from atlas.core.graphs import QUERIES
from atlas.core.git_env import clean_git_env
from atlas.memory.project_graph import DEFAULT_GRAPH_DB


def _rows(result: Any) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    while result.has_next():
        out.append(tuple(result.get_next()))
    return out


def build_graph_server(
    db_path: Path,
    *,
    repo_root: Path | None = None,
    name: str = "atlas-graph",
) -> "FastMCP":
    """Construye el server. Abre la BD en modo solo-lectura por llamada (la
    regeneración escribe desde otro proceso; el lock de Kuzu es por conexión)."""
    import kuzu
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    def _connect() -> tuple[Any, Any]:
        db = kuzu.Database(str(db_path), read_only=True)
        return db, kuzu.Connection(db)

    def _query(cypher: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        db, conn = _connect()
        try:
            return _rows(conn.execute(cypher, parameters=params or {}))
        finally:
            conn.close()
            db.close()

    def _head_sha() -> str:
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
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    # A stdio MCP process imports its implementation once. The project graph
    # can be atomically rebuilt underneath it, but that must not make an old
    # server binary look current after HEAD advances. Capture the deployment
    # revision and require a process restart before serving present-tense
    # dependency answers for a newer checkout.
    server_started_head_sha = _head_sha()

    def _source_tree_dirty() -> bool | None:
        """Whether committed graph inputs differ from the working tree.

        The project graph is intentionally built from ``git show`` snapshots of
        ``src/atlas``.  Matching HEAD alone is therefore insufficient while an
        agent is editing source files: those edits are not represented in Kuzu.
        ``None`` means the check itself could not be trusted.
        """
        if repo_root is None:
            return None
        try:
            result = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--",
                    "src/atlas",
                ],
                cwd=repo_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return bool(result.stdout.strip())

    def _latest_snapshot() -> tuple[str, int, Any] | None:
        rows = _query(
            "MATCH (v:FileVersion) "
            "RETURN v.commit_sha, count(*), max(v.ingested_at) AS t "
            "ORDER BY t DESC LIMIT 1"
        )
        if not rows:
            return None
        return str(rows[0][0]), int(rows[0][1]), rows[0][2]

    def _freshness() -> tuple[str, str, str, bool | None]:
        latest = _latest_snapshot()
        graph_sha = latest[0] if latest else ""
        head_sha = _head_sha()
        source_dirty = _source_tree_dirty()
        if not graph_sha:
            return "EMPTY", graph_sha, head_sha, source_dirty
        if not head_sha or source_dirty is None:
            return "UNKNOWN", graph_sha, head_sha, source_dirty
        if graph_sha != head_sha:
            return "STALE", graph_sha, head_sha, source_dirty
        if source_dirty:
            return "DIRTY", graph_sha, head_sha, source_dirty
        if not server_started_head_sha:
            return "UNKNOWN", graph_sha, head_sha, source_dirty
        if server_started_head_sha != head_sha:
            return "SERVER_STALE", graph_sha, head_sha, source_dirty
        return "FRESH", graph_sha, head_sha, source_dirty

    def _require_fresh_sha() -> str:
        status, graph_sha, head_sha, source_dirty = _freshness()
        if status != "FRESH":
            raise RuntimeError(
                "project graph freshness is "
                f"{status}: graph_commit_sha={graph_sha or '<none>'}, "
                f"head_sha={head_sha or '<unavailable>'}, "
                f"server_started_head_sha={server_started_head_sha or '<unavailable>'}, "
                f"source_tree_dirty={source_dirty}"
            )
        return graph_sha

    @server.tool()
    def graph_overview() -> dict[str, Any]:
        """Radiografía del grafo: commits ingeridos, nº de módulos, top hubs por
        fan-in (los módulos de los que más depende el resto de Atlas)."""
        snapshots = _query(
            "MATCH (v:FileVersion) "
            "RETURN v.commit_sha, max(v.ingested_at) AS t ORDER BY t"
        )
        latest = _latest_snapshot()
        hubs: list[tuple[Any, ...]] = []
        if latest:
            hubs = _query(
                "MATCH (a:FileVersion)-[:IMPORTS]->(b:FileVersion) "
                "WHERE b.commit_sha = $sha "
                "RETURN b.path, count(a) AS fan_in ORDER BY fan_in DESC LIMIT 10",
                {"sha": latest[0]},
            )
        freshness, graph_sha, head_sha, source_dirty = _freshness()
        return {
            "commits_ingested": [str(row[0]) for row in snapshots],
            "graph_commit_sha": graph_sha,
            "head_sha": head_sha,
            "server_started_head_sha": server_started_head_sha,
            "freshness": freshness,
            "source_tree_dirty": source_dirty,
            "modules_latest": latest[1] if latest else 0,
            "top_hubs_by_fan_in": [{"module": h[0], "fan_in": h[1]} for h in hubs],
        }

    @server.tool()
    def graph_importers(module: str, commit_sha: str = "") -> list[str]:
        """Quién importa `module` (directo). `module` en forma atlas.x.y;
        sin `commit_sha` usa el último commit ingerido."""
        sha = commit_sha or _latest_sha()
        return [r[0] for r in _query(QUERIES["direct_importers"], {"path": module, "sha": sha})]

    @server.tool()
    def graph_blast_radius(module: str, commit_sha: str = "") -> list[str]:
        """Radio de impacto: todo lo que depende de `module` hasta 4 saltos —
        qué se rompe en cascada si cambias este fichero."""
        sha = commit_sha or _latest_sha()
        return [r[0] for r in _query(QUERIES["blast_radius"], {"path": module, "sha": sha})]

    @server.tool()
    def graph_lineage(module: str) -> list[dict[str, Any]]:
        """Linaje temporal de `module`: su hash de contenido en cada commit
        ingerido — cuándo cambió de verdad (no solo cuándo se tocó)."""
        return [
            {"commit_sha": r[0], "hash": r[1], "ingested_at": str(r[2])}
            for r in _query(QUERIES["temporal_lineage"], {"path": module})
        ]

    @server.tool()
    def graph_churn() -> list[dict[str, Any]]:
        """Los 10 módulos que más mutan entre los commits ingeridos — dónde
        está el trabajo (y el riesgo) de verdad."""
        return [
            {"module": r[0], "times_modified": r[1]}
            for r in _query(QUERIES["most_changed_files"])
        ]

    @server.tool()
    def graph_imports_of(module: str, commit_sha: str = "") -> list[str]:
        """Qué importa `module` (sus dependencias directas)."""
        sha = commit_sha or _latest_sha()
        return [
            r[0]
            for r in _query(
                "MATCH (a:FileVersion)-[:IMPORTS]->(b:FileVersion) "
                "WHERE a.path = $path AND a.commit_sha = $sha RETURN b.path",
                {"path": module, "sha": sha},
            )
        ]

    @server.tool()
    def graph_note_neighborhood(note_stem: str) -> dict[str, Any]:
        """Vecindario de una nota Obsidian del vault del proyecto (si está
        cargado): a qué enlaza y quién la enlaza."""
        out = _query(
            "MATCH (a:ObsidianNote)-[:LINKS_TO]->(b:ObsidianNote) "
            "WHERE a.path ENDS WITH $f RETURN b.path LIMIT 25",
            {"f": f"{note_stem}.md"},
        )
        inc = _query(
            "MATCH (a:ObsidianNote)-[:LINKS_TO]->(b:ObsidianNote) "
            "WHERE b.path ENDS WITH $f RETURN a.path LIMIT 25",
            {"f": f"{note_stem}.md"},
        )
        return {"links_to": [r[0] for r in out], "linked_from": [r[0] for r in inc]}

    @server.tool()
    def graph_callers(symbol: str) -> dict[str, Any]:
        """Quién llama a `symbol` (match por sufijo de nombre, hasta 25).
        `symbol` es el nombre tal como lo emite graphify (ej. ".start()" o
        "ThermalWatchdog") — no hace falta el nombre completo cualificado."""
        try:
            rows = _query(
                "MATCH (a:Symbol)-[c:CALLS]->(b:Symbol) WHERE b.name ENDS WITH $s "
                "RETURN a.name, a.source_file, a.source_location, c.confidence LIMIT 25",
                {"s": symbol},
            )
        except RuntimeError as exc:
            if "does not exist" in str(exc):
                return {"error": "call-graph no ingerido aún"}
            raise
        return {
            "callers": [
                {"name": r[0], "source_file": r[1], "source_location": r[2], "confidence": r[3]}
                for r in rows
            ]
        }

    @server.tool()
    def graph_callees(symbol: str) -> dict[str, Any]:
        """A quién llama `symbol` (match por sufijo de nombre, hasta 25)."""
        try:
            rows = _query(
                "MATCH (a:Symbol)-[c:CALLS]->(b:Symbol) WHERE a.name ENDS WITH $s "
                "RETURN b.name, b.source_file, b.source_location, c.confidence LIMIT 25",
                {"s": symbol},
            )
        except RuntimeError as exc:
            if "does not exist" in str(exc):
                return {"error": "call-graph no ingerido aún"}
            raise
        return {
            "callees": [
                {"name": r[0], "source_file": r[1], "source_location": r[2], "confidence": r[3]}
                for r in rows
            ]
        }

    def _latest_sha() -> str:
        return _require_fresh_sha()

    return server


def serve(
    repo_root: Path | None = None,
    db_path: Path | None = None,
    *,
    name: str = "atlas-graph",
) -> None:
    """Punto de entrada stdio."""
    root = repo_root or Path(os.environ.get("ATLAS_CORE_ROOT", Path.cwd()))
    server = build_graph_server(db_path or DEFAULT_GRAPH_DB, repo_root=root, name=name)
    server.run()


if __name__ == "__main__":
    import sys

    serve(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
