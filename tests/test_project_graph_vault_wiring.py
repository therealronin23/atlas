"""F3.2 (toasty-hatching-pillow) — vault-wiring del tick del grafo.

``maintenance_project_graph_tick`` llamaba a ``build_project_graph`` SIN
``vault_root`` (hallazgo C2, 2026-07-15): las tablas ObsidianNote/LINKS_TO
jamás llegaban a la BD de producción y ``graph_note_neighborhood`` respondía
vacío/reventaba. Contrato fijado aquí:

- default: ``<repo>/graphify-vault`` (donde graphify deja el vault del repo);
- override: env ``ATLAS_OBSIDIAN_VAULT`` (mismo patrón que
  ``ATLAS_PROJECT_GRAPH_DB``: ``Path(env).expanduser()``);
- end-to-end: un vault sintético atraviesa el tick real y deja filas en
  ObsidianNote/LINKS_TO de la BD servida (tras el swap).

Los dos primeros tests monkeypatchean build_project_graph (cero Kuzu); el
end-to-end usa Kuzu real sobre un repo/vault mínimos (mismo coste que
tests/test_project_graph.py).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import kuzu
import pytest

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    # La marca anti-recursión viene puesta cuando la suite corre dentro del
    # lazo — estos tests ejercitan el tick de verdad (mismo criterio que
    # tests/test_self_improvement_wiring.py).
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    monkeypatch.delenv("ATLAS_OBSIDIAN_VAULT", raising=False)
    monkeypatch.delenv("ATLAS_PROJECT_GRAPH", raising=False)
    monkeypatch.delenv("ATLAS_PROJECT_GRAPH_DB", raising=False)
    monkeypatch.delenv("ATLAS_MEMORY_DB", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _git_repo(repo: Path) -> None:
    atlas_dir = repo / "src" / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)
    (atlas_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo, check=True,
    )


def _ast_cache(repo: Path) -> None:
    """Cache AST graphify mínimo y VÁLIDO para el contrato estricto del tick
    (symbols>0 y files>0 bajo src/atlas; mismo esquema real que
    tests/test_callgraph_to_kuzu.py)."""
    cache = repo / "graphify-out" / "cache" / "ast" / "v0.9.11"
    cache.mkdir(parents=True, exist_ok=True)
    payload = {
        "nodes": [
            {
                "id": "mod_a_py",
                "label": "a.py",
                "file_type": "code",
                "source_file": "src/atlas/a.py",
                "source_location": "L1",
            },
            {
                "id": "mod_a_foo",
                "label": ".foo()",
                "file_type": "code",
                "source_file": "src/atlas/a.py",
                "source_location": "L5",
                "_callable": True,
            },
        ],
        "edges": [
            {
                "source": "mod_a_py",
                "target": "mod_a_foo",
                "relation": "contains",
                "confidence": "EXTRACTED",
                "source_file": "src/atlas/a.py",
                "source_location": "L5",
                "weight": 1.0,
            },
        ],
        "raw_calls": [],
    }
    (cache / ("a" * 64 + ".json")).write_text(json.dumps(payload), encoding="utf-8")


def _tick_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
    db = tmp_path / "graphdb" / "project_graph.kuzu"
    monkeypatch.setenv("ATLAS_PROJECT_GRAPH_DB", str(db))
    repo = tmp_path / "repo"
    _git_repo(repo)
    _ast_cache(repo)
    return repo, db


def _fake_callgraph(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"files": 1, "symbols": 2, "calls": 1}


class TestVaultWiring:
    def test_tick_passes_default_vault_root(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, _db = _tick_env(tmp_path, monkeypatch)

        captured: dict[str, Any] = {}

        def _fake_build(root: Path, db_path: Path, **kw: Any) -> dict[str, Any]:
            captured.update(kw)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_text("kuzu-fake", encoding="utf-8")
            return {"commits": ["abc"]}

        monkeypatch.setattr(
            "atlas.memory.project_graph.build_project_graph", _fake_build
        )
        monkeypatch.setattr(
            "atlas.memory.callgraph_to_kuzu.load_callgraph_into_kuzu", _fake_callgraph
        )

        assert orch.maintenance_project_graph_tick()["status"] == "ran"
        assert captured["vault_root"] == repo.resolve() / "graphify-vault"

    def test_tick_honours_atlas_obsidian_vault_env(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _repo, _db = _tick_env(tmp_path, monkeypatch)
        override = tmp_path / "otro-vault"
        monkeypatch.setenv("ATLAS_OBSIDIAN_VAULT", str(override))

        captured: dict[str, Any] = {}

        def _fake_build(root: Path, db_path: Path, **kw: Any) -> dict[str, Any]:
            captured.update(kw)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_text("kuzu-fake", encoding="utf-8")
            return {"commits": ["abc"]}

        monkeypatch.setattr(
            "atlas.memory.project_graph.build_project_graph", _fake_build
        )
        monkeypatch.setattr(
            "atlas.memory.callgraph_to_kuzu.load_callgraph_into_kuzu", _fake_callgraph
        )

        assert orch.maintenance_project_graph_tick()["status"] == "ran"
        assert captured["vault_root"] == override

    def test_tick_ingests_synthetic_vault_end_to_end(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vault sintético en la ruta default → tick REAL (sin monkeypatch de
        build) → la BD servida tiene ObsidianNote y LINKS_TO con filas."""
        repo, db = _tick_env(tmp_path, monkeypatch)
        vault = repo / "graphify-vault"
        vault.mkdir()
        (vault / "a.md").write_text(
            "---\ntitle: Nota A\n---\nEnlaza a [[b]].", encoding="utf-8"
        )
        (vault / "b.md").write_text("Vuelve a [[a]]", encoding="utf-8")

        result = orch.maintenance_project_graph_tick()

        assert result["status"] == "ran"
        assert result["metrics"]["vault"] == {"notes": 2, "links": 2, "unresolved": 0}

        kdb = kuzu.Database(str(db), read_only=True)
        conn = kuzu.Connection(kdb)
        try:
            r = conn.execute("MATCH (n:ObsidianNote) RETURN count(n)")
            assert r.get_next()[0] == 2
            r = conn.execute("MATCH ()-[l:LINKS_TO]->() RETURN count(l)")
            assert r.get_next()[0] == 2
        finally:
            conn.close()
            kdb.close()
