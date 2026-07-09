"""Tests — grafo vivo del proyecto + shell MCP de consulta (graph_server)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.memory.project_graph import build_project_graph, recent_commits


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    atlas_dir = repo / "src" / "atlas"
    atlas_dir.mkdir(parents=True)

    (atlas_dir / "a.py").write_text("X = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "c1")

    (atlas_dir / "b.py").write_text("from atlas import a\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "c2")
    return repo


def test_recent_commits_chronological(tiny_repo: Path) -> None:
    shas = recent_commits(tiny_repo, 10)
    assert len(shas) == 2
    # Orden viejo→nuevo: el primero es c1.
    assert _git(tiny_repo, "rev-list", "--max-parents=0", "HEAD") == shas[0]


def test_build_project_graph_and_server_queries(tiny_repo: Path, tmp_path: Path) -> None:
    """El grafo se construye y las tools del server responden sobre él."""
    db_path = tmp_path / "pg.kuzu"
    metrics = build_project_graph(tiny_repo, db_path, commits=10)
    assert metrics["bitemporal"]["nodes"] > 0

    mcp = pytest.importorskip("mcp.server.fastmcp")  # SDK opcional
    del mcp
    from atlas.mcp.graph_server import build_graph_server

    server = build_graph_server(db_path)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert {"graph_overview", "graph_importers", "graph_blast_radius", "graph_lineage"} <= set(tools)

    overview = tools["graph_overview"].fn()
    assert overview["modules_latest"] == 2
    assert len(overview["commits_ingested"]) == 2

    importers = tools["graph_importers"].fn(module="atlas.a")
    assert importers == ["atlas.b"]

    blast = tools["graph_blast_radius"].fn(module="atlas.a")
    assert "atlas.b" in blast

    lineage = tools["graph_lineage"].fn(module="atlas.a")
    assert len(lineage) == 2  # presente en ambos commits


def test_build_is_idempotent(tiny_repo: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "pg.kuzu"
    m1 = build_project_graph(tiny_repo, db_path, commits=10)
    m2 = build_project_graph(tiny_repo, db_path, commits=10)
    assert m1["bitemporal"]["nodes"] == m2["bitemporal"]["nodes"]
