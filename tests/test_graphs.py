"""Tests — grafo de imports bitemporal sobre Kuzu (src/atlas/core/graphs.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import kuzu
import pytest

from atlas.core.graphs import QUERIES, build_bitemporal_graph, load_bitemporal_into_kuzu
from atlas.memory.embeddings import StubEmbedder


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def tiny_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    """Repo git minimo, 3 commits reales sobre src/atlas:

    c1: solo a.py
    c2: + b.py (importa a) -> atlas.b es "added"
    c3: a.py cambia de contenido -> atlas.a es "modified"
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")

    atlas_dir = repo / "src" / "atlas"
    atlas_dir.mkdir(parents=True)

    (atlas_dir / "a.py").write_text("X = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "c1: solo a")
    sha1 = _git(repo, "rev-parse", "HEAD")

    (atlas_dir / "b.py").write_text("from atlas import a\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "c2: b importa a")
    sha2 = _git(repo, "rev-parse", "HEAD")

    (atlas_dir / "a.py").write_text("X = 2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "c3: a modificado")
    sha3 = _git(repo, "rev-parse", "HEAD")

    return repo, [sha1, sha2, sha3]


def test_build_bitemporal_graph_diffs(tiny_repo: tuple[Path, list[str]]) -> None:
    repo, shas = tiny_repo
    result = build_bitemporal_graph(repo, shas)

    assert len(result["diffs"]) == 2
    assert result["diffs"][0]["added"] == ["atlas.b"]
    assert result["diffs"][0]["removed"] == []
    assert result["diffs"][1]["modified"] == ["atlas.a"]
    assert "atlas.a" in result["snapshots"][shas[1]]["atlas.b"]["imports"]


def test_load_bitemporal_into_kuzu_no_drift(tiny_repo: tuple[Path, list[str]], tmp_path: Path) -> None:
    """Reingerir los mismos 3 commits no duplica nodos ni aristas (MERGE por id)."""
    repo, shas = tiny_repo
    db_path = tmp_path / "graphs.kuzu"
    embedder = StubEmbedder(dim=8)

    metrics_1 = load_bitemporal_into_kuzu(repo, db_path, shas, embedder=embedder)
    metrics_2 = load_bitemporal_into_kuzu(repo, db_path, shas, embedder=embedder)

    assert metrics_1["nodes"] > 0
    assert metrics_1 == metrics_2

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:FileVersion) RETURN count(n)")
        assert r.get_next()[0] == metrics_1["nodes"]
    finally:
        conn.close()
        db.close()


def test_queries_diffs_impact_lineage(tiny_repo: tuple[Path, list[str]], tmp_path: Path) -> None:
    repo, shas = tiny_repo
    db_path = tmp_path / "graphs.kuzu"
    load_bitemporal_into_kuzu(repo, db_path, shas, embedder=StubEmbedder(dim=8))

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        # 1. diff_modified: atlas.a cambió de c2 -> c3.
        r = conn.execute(QUERIES["diff_modified"], parameters={"from_sha": shas[1], "to_sha": shas[2]})
        rows = list(_drain(r))
        assert any(row[0] == "atlas.a" for row in rows)

        # 2. temporal_lineage: atlas.a aparece en los 3 commits, con 2 hashes distintos.
        r = conn.execute(QUERIES["temporal_lineage"], parameters={"path": "atlas.a"})
        rows = list(_drain(r))
        assert len(rows) == 3
        assert len({row[1] for row in rows}) == 2

        # 3. direct_importers: en c2/c3, atlas.b importa directamente atlas.a.
        r = conn.execute(QUERIES["direct_importers"], parameters={"path": "atlas.a", "sha": shas[2]})
        rows = list(_drain(r))
        assert rows == [("atlas.b",)]

        # 4. blast_radius: mismo resultado a 1-4 saltos (grafo pequeño, sin transitividad extra).
        r = conn.execute(QUERIES["blast_radius"], parameters={"path": "atlas.a", "sha": shas[2]})
        rows = list(_drain(r))
        assert ("atlas.b",) in rows

        # 5. most_changed_files: atlas.a mutó una vez (c2->c3).
        r = conn.execute(QUERIES["most_changed_files"])
        rows = list(_drain(r))
        assert ("atlas.a", 1) in rows
    finally:
        conn.close()
        db.close()


def _drain(result: object) -> list[tuple]:
    rows = []
    while result.has_next():  # type: ignore[attr-defined]
        rows.append(tuple(result.get_next()))  # type: ignore[attr-defined]
    return rows
