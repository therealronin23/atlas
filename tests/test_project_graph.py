"""Tests — grafo vivo del proyecto + shell MCP de consulta (graph_server)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import kuzu
import pytest

from atlas.memory.project_graph import (
    build_project_graph,
    recent_commits,
    resolve_graph_embedder,
)


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

    server = build_graph_server(db_path, repo_root=tiny_repo)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert {"graph_overview", "graph_importers", "graph_blast_radius", "graph_lineage"} <= set(tools)

    overview = tools["graph_overview"].fn()
    assert overview["modules_latest"] == 2
    assert len(overview["commits_ingested"]) == 2
    assert overview["graph_commit_sha"] == _git(tiny_repo, "rev-parse", "HEAD")
    assert overview["head_sha"] == overview["graph_commit_sha"]
    assert overview["freshness"] == "FRESH"
    assert overview["source_tree_dirty"] is False

    importers = tools["graph_importers"].fn(module="atlas.a")
    assert importers == ["atlas.b"]

    blast = tools["graph_blast_radius"].fn(module="atlas.a")
    assert "atlas.b" in blast

    lineage = tools["graph_lineage"].fn(module="atlas.a")
    assert len(lineage) == 2  # presente en ambos commits


def test_overview_selects_latest_snapshot_not_the_one_with_most_modules(
    tiny_repo: Path, tmp_path: Path
) -> None:
    """El último snapshot puede ser menor: conteo máximo no equivale a actualidad."""
    (tiny_repo / "src" / "atlas" / "b.py").unlink()
    _git(tiny_repo, "add", "-A")
    _git(tiny_repo, "commit", "-q", "-m", "c3-removes-module")
    db_path = tmp_path / "pg.kuzu"
    build_project_graph(tiny_repo, db_path, commits=10)

    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    server = build_graph_server(db_path, repo_root=tiny_repo)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    overview = tools["graph_overview"].fn()

    assert overview["graph_commit_sha"] == _git(tiny_repo, "rev-parse", "HEAD")
    assert overview["modules_latest"] == 1
    assert overview["freshness"] == "FRESH"


def test_current_queries_fail_explicitly_when_graph_is_stale(
    tiny_repo: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "pg.kuzu"
    build_project_graph(tiny_repo, db_path, commits=10)
    graph_head = _git(tiny_repo, "rev-parse", "HEAD")

    (tiny_repo / "src" / "atlas" / "c.py").write_text(
        "from atlas import a\n", encoding="utf-8"
    )
    _git(tiny_repo, "add", ".")
    _git(tiny_repo, "commit", "-q", "-m", "c3-after-graph")

    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    server = build_graph_server(db_path, repo_root=tiny_repo)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    overview = tools["graph_overview"].fn()

    assert overview["graph_commit_sha"] == graph_head
    assert overview["head_sha"] == _git(tiny_repo, "rev-parse", "HEAD")
    assert overview["freshness"] == "STALE"
    with pytest.raises(RuntimeError, match="STALE"):
        tools["graph_importers"].fn(module="atlas.a")

    # Una consulta histórica explícita sigue siendo válida y no finge actualidad.
    assert tools["graph_importers"].fn(module="atlas.a", commit_sha=graph_head) == [
        "atlas.b"
    ]


def test_current_queries_fail_explicitly_when_source_tree_is_dirty(
    tiny_repo: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "pg.kuzu"
    build_project_graph(tiny_repo, db_path, commits=10)
    (tiny_repo / "src" / "atlas" / "a.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )

    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    server = build_graph_server(db_path, repo_root=tiny_repo)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    overview = tools["graph_overview"].fn()

    assert overview["graph_commit_sha"] == _git(tiny_repo, "rev-parse", "HEAD")
    assert overview["head_sha"] == overview["graph_commit_sha"]
    assert overview["source_tree_dirty"] is True
    assert overview["freshness"] == "DIRTY"
    with pytest.raises(RuntimeError, match="DIRTY"):
        tools["graph_importers"].fn(module="atlas.a")


def test_current_queries_fail_when_server_process_predates_current_head(
    tiny_repo: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "pg.kuzu"
    build_project_graph(tiny_repo, db_path, commits=10)

    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    server = build_graph_server(db_path, repo_root=tiny_repo)
    tools = {tool.name: tool for tool in server._tool_manager.list_tools()}
    started_head = _git(tiny_repo, "rev-parse", "HEAD")

    (tiny_repo / "src" / "atlas" / "c.py").write_text(
        "from atlas import a\n", encoding="utf-8"
    )
    _git(tiny_repo, "add", ".")
    _git(tiny_repo, "commit", "-q", "-m", "c3-server-stays-open")
    build_project_graph(tiny_repo, db_path, commits=10)

    overview = tools["graph_overview"].fn()
    assert overview["graph_commit_sha"] == _git(tiny_repo, "rev-parse", "HEAD")
    assert overview["head_sha"] == overview["graph_commit_sha"]
    assert overview["server_started_head_sha"] == started_head
    assert overview["freshness"] == "SERVER_STALE"
    with pytest.raises(RuntimeError, match="SERVER_STALE"):
        tools["graph_importers"].fn(module="atlas.a")

    refreshed_server = build_graph_server(db_path, repo_root=tiny_repo)
    refreshed_tools = {
        tool.name: tool for tool in refreshed_server._tool_manager.list_tools()
    }
    assert refreshed_tools["graph_overview"].fn()["freshness"] == "FRESH"


def test_build_is_idempotent(tiny_repo: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "pg.kuzu"
    m1 = build_project_graph(tiny_repo, db_path, commits=10)
    m2 = build_project_graph(tiny_repo, db_path, commits=10)
    assert m1["bitemporal"]["nodes"] == m2["bitemporal"]["nodes"]


class _FakeEmbedder8:
    """Embedder fake determinista, dim=8, sin red — solo para asertar propagación."""

    @property
    def dim(self) -> int:
        return 8

    def embed(self, text: str) -> list[float]:
        return [float(len(text) % 8)] * 8


def test_build_project_graph_propagates_embedder(tiny_repo: Path, tmp_path: Path) -> None:
    """embedder=... llega hasta load_bitemporal_into_kuzu (no se queda en el default stub dim=64)."""
    db_path = tmp_path / "pg.kuzu"
    metrics = build_project_graph(tiny_repo, db_path, commits=10, embedder=_FakeEmbedder8())
    assert metrics["bitemporal"]["nodes"] > 0

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:FileVersion) RETURN n.embedding LIMIT 1")
        assert not isinstance(r, list)
        emb = cast(list[Any], r.get_next())[0]
        assert len(emb) == 8
    finally:
        conn.close()
        db.close()


def test_build_project_graph_default_embedder_is_unchanged(tiny_repo: Path, tmp_path: Path) -> None:
    """Sin `embedder=`, el comportamiento es EXACTO al de antes: stub dim=64."""
    db_path = tmp_path / "pg.kuzu"
    build_project_graph(tiny_repo, db_path, commits=10)

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:FileVersion) RETURN n.embedding LIMIT 1")
        assert not isinstance(r, list)
        emb = cast(list[Any], r.get_next())[0]
        assert len(emb) == 64
    finally:
        conn.close()
        db.close()


def test_resolve_graph_embedder_empty_or_stub_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_GRAPH_EMBEDDER", raising=False)
    assert resolve_graph_embedder() is None

    monkeypatch.setenv("ATLAS_GRAPH_EMBEDDER", "")
    assert resolve_graph_embedder() is None

    monkeypatch.setenv("ATLAS_GRAPH_EMBEDDER", "stub")
    assert resolve_graph_embedder() is None


def test_resolve_graph_embedder_fastembed_without_loading_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """'fastembed' delega en atlas.memory.embeddings.default_embedder() — el test no debe
    pagar la carga real del modelo ONNX, así que se monkeypatchea la fábrica."""
    import atlas.memory.embeddings as embeddings_mod

    class _FakeSemanticEmbedder:
        @property
        def dim(self) -> int:
            return 384

        def embed(self, text: str) -> list[float]:  # pragma: no cover - no se llama
            raise AssertionError("no debería invocarse en este test")

    monkeypatch.setattr(embeddings_mod, "default_embedder", lambda: _FakeSemanticEmbedder())
    monkeypatch.setenv("ATLAS_GRAPH_EMBEDDER", "fastembed")

    embedder = resolve_graph_embedder()
    assert embedder is not None
    assert embedder.dim == 384
