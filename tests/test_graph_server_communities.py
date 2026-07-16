"""F3.5 (toasty-hatching-pillow) — comunidades semánticas como tools del tronco.

La semántica de graphify (notas ``_COMMUNITY_*`` con ``type: community`` +
``cohesion`` en frontmatter, miembros como wikilinks resueltos → LINKS_TO)
existe en el vault y, tras F3.2/F3.4, llega a la BD servida. Estas tools la
exponen por MCP con el mismo contrato defensivo que graph_note_neighborhood:
BD sin tablas → mensaje limpio, jamás un stacktrace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import kuzu
import pytest

from atlas.mcp.graph_server import build_graph_server

_SCHEMA = (
    "CREATE NODE TABLE IF NOT EXISTS ObsidianNote("
    "path STRING, title STRING, note_type STRING, community STRING, cohesion DOUBLE, "
    "tags STRING[], ingested_at TIMESTAMP, PRIMARY KEY(path))",
    "CREATE REL TABLE IF NOT EXISTS LINKS_TO(FROM ObsidianNote TO ObsidianNote)",
)


def _seed_vault_db(db_path: Path) -> None:
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        for stmt in _SCHEMA:
            conn.execute(stmt)
        for path, title, note_type, cohesion in (
            ("_COMMUNITY_nucleo.md", "Núcleo Atlas", "community", 0.82),
            ("a.md", "Nota A", "", None),
            ("b.md", "Nota B", "", None),
            ("suelta.md", "Sin comunidad", "", None),
        ):
            conn.execute(
                "CREATE (:ObsidianNote {path: $p, title: $t, note_type: $nt, "
                "community: '', cohesion: $c})",
                parameters={"p": path, "t": title, "nt": note_type, "c": cohesion},
            )
        for member in ("a.md", "b.md"):
            conn.execute(
                "MATCH (c:ObsidianNote {path: $c}), (m:ObsidianNote {path: $m}) "
                "CREATE (c)-[:LINKS_TO]->(m)",
                parameters={"c": "_COMMUNITY_nucleo.md", "m": member},
            )
    finally:
        conn.close()
        db.close()


def _tools(db_path: Path) -> dict[str, Any]:
    server = build_graph_server(db_path)
    return {t.name: t for t in server._tool_manager.list_tools()}


@pytest.fixture
def vault_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "graph.kuzu"
    _seed_vault_db(db_path)
    return db_path


def test_graph_communities_lists_cohesion_and_members(vault_db: Path) -> None:
    out = _tools(vault_db)["graph_communities"].fn()
    assert out["communities"] == [
        {
            "path": "_COMMUNITY_nucleo.md",
            "title": "Núcleo Atlas",
            "cohesion": 0.82,
            "members": 2,
        }
    ]


def test_graph_semantic_neighbors_shares_community_not_self(vault_db: Path) -> None:
    out = _tools(vault_db)["graph_semantic_neighbors"].fn(note_stem="a")
    paths = [n["path"] for n in out["neighbors"]]
    assert paths == ["b.md"]  # ni a.md (self) ni suelta.md (sin comunidad)
    assert out["neighbors"][0]["community"] == "Núcleo Atlas"


def test_both_tools_survive_db_without_vault_tables(tmp_path: Path) -> None:
    """Mismo contrato que graph_note_neighborhood: BD recién creada sin
    ObsidianNote → mensaje limpio, no RuntimeError."""
    db_path = tmp_path / "empty.kuzu"
    db = kuzu.Database(str(db_path))
    kuzu.Connection(db).close()
    db.close()
    tools = _tools(db_path)
    assert tools["graph_communities"].fn() == {"error": "vault no ingerido aún"}
    assert tools["graph_semantic_neighbors"].fn(note_stem="a") == {
        "error": "vault no ingerido aún"
    }
