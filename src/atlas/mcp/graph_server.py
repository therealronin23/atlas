"""Shell FastMCP del grafo del proyecto — consultar Atlas sin leer documentos.

Sirve las queries del grafo vivo (``atlas.memory.project_graph``) por MCP:
quién importa un módulo, radio de impacto transitivo, linaje temporal de un
fichero, churn, y vecindario de notas Obsidian. El objetivo es que cualquier
IA conectada al tronco entienda la estructura REAL de Atlas con una query
barata en vez de quemar tokens leyendo .md (que son pasado/futuro, no presente).

Mismo patrón de capa-transporte que ``memory_server``/``knowledge_server``:
SDK `mcp` opcional, import diferido, sin lógica de dominio aquí.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from atlas.core.graphs import QUERIES
from atlas.memory.project_graph import DEFAULT_GRAPH_DB


def _rows(result: Any) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    while result.has_next():
        out.append(tuple(result.get_next()))
    return out


def build_graph_server(db_path: Path, *, name: str = "atlas-graph") -> "FastMCP":
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

    @server.tool()
    def graph_overview() -> dict[str, Any]:
        """Radiografía del grafo: commits ingeridos, nº de módulos, top hubs por
        fan-in (los módulos de los que más depende el resto de Atlas)."""
        shas = _query(
            "MATCH (v:FileVersion) RETURN DISTINCT v.commit_sha ORDER BY v.commit_sha"
        )
        latest = _query(
            "MATCH (v:FileVersion) RETURN v.commit_sha, count(*) "
            "ORDER BY count(*) DESC LIMIT 1"
        )
        hubs: list[tuple[Any, ...]] = []
        if latest:
            hubs = _query(
                "MATCH (a:FileVersion)-[:IMPORTS]->(b:FileVersion) "
                "WHERE b.commit_sha = $sha "
                "RETURN b.path, count(a) AS fan_in ORDER BY fan_in DESC LIMIT 10",
                {"sha": latest[0][0]},
            )
        return {
            "commits_ingested": [s[0] for s in shas],
            "modules_latest": latest[0][1] if latest else 0,
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

    def _latest_sha() -> str:
        rows = _query(
            "MATCH (v:FileVersion) RETURN v.commit_sha, max(v.ingested_at) AS t "
            "ORDER BY t DESC LIMIT 1"
        )
        return str(rows[0][0]) if rows else ""

    return server


def serve(db_path: Path | None = None, *, name: str = "atlas-graph") -> None:
    """Punto de entrada stdio."""
    server = build_graph_server(db_path or DEFAULT_GRAPH_DB, name=name)
    server.run()


if __name__ == "__main__":
    import sys

    serve(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
