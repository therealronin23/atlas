"""
Capa 3 — backend de worker. WorktreeManager se prueba contra un repo git
temporal (hermético, sin red, patrón de test_reality). La lógica de
WorktreeWorker se prueba con manager y callables fake.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from atlas.core.swarm_backend import WorktreeManager, WorktreeWorker
from atlas.core.verify import ArtifactKind, Check, CostTier, Evidence, Verdict


def _clean_env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX", "GIT_COMMON_DIR"):
        env.pop(var, None)
    return env


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, env=_clean_env(), check=True, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "demo.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)
    return root


def _evidence(passed: bool) -> Evidence:
    return Evidence(
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        checks=(Check(name="suite", passed=passed, cost=CostTier.SUITE),),
        total_cost=CostTier.SUITE,
        verifier_ids=("worktree.suite",),
    )


class TestWorktreeManager:
    def test_create_yields_isolated_checkout(self, repo: Path) -> None:
        mgr = WorktreeManager(repo)
        path = mgr.create("w1")
        try:
            assert path.exists()
            assert (path / "demo.py").read_text(encoding="utf-8") == "x = 1\n"
            assert path.resolve() != repo.resolve()
        finally:
            mgr.teardown(path)
        assert not path.exists()

    def test_session_context_manager_tears_down(self, repo: Path) -> None:
        mgr = WorktreeManager(repo)
        captured: dict[str, Path] = {}
        with mgr.session("w2") as path:
            captured["p"] = path
            assert path.exists()
        assert not captured["p"].exists()

    def test_edits_in_worktree_do_not_touch_root(self, repo: Path) -> None:
        mgr = WorktreeManager(repo)
        with mgr.session("w3") as path:
            (path / "demo.py").write_text("x = 999\n", encoding="utf-8")
        # El root quedó intacto: el worktree era detached y desechable.
        assert (repo / "demo.py").read_text(encoding="utf-8") == "x = 1\n"

    def test_teardown_refuses_to_delete_root(self, repo: Path) -> None:
        mgr = WorktreeManager(repo)
        # teardown sobre el propio root no debe borrarlo (guard de la rama defensiva)
        mgr.teardown(repo)
        assert (repo / "demo.py").exists()

    def test_immune_to_ambient_git_env(self, repo: Path, monkeypatch) -> None:
        # Regresión 2026-06-13: bajo un hook git (pre-commit), GIT_DIR/
        # GIT_INDEX_FILE están seteados y secuestraban el worktree hacia el
        # repo del hook → 365 worktrees huérfanos + pre-commit flaky. El
        # manager debe limpiar esas vars y operar sobre SU repo.
        other = repo.parent / "otro.git"
        monkeypatch.setenv("GIT_DIR", str(other))
        monkeypatch.setenv("GIT_INDEX_FILE", str(other / "index"))
        mgr = WorktreeManager(repo)
        with mgr.session("w-env") as path:
            assert (path / "demo.py").read_text(encoding="utf-8") == "x = 1\n"
        assert not other.exists()  # nunca tocó el repo secuestrado


class FakeManager:
    """Manager fake: no git real, solo entrega un path temporal y registra."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.created: list[str] = []
        self.torn_down = 0

    @contextmanager
    def session(self, name: str, *, base_ref: str = "HEAD") -> Iterator[Path]:
        self.created.append(name)
        try:
            yield self._path
        finally:
            self.torn_down += 1


class TestWorktreeWorker:
    def test_produce_builds_patch_artifact_with_validation(self, tmp_path: Path) -> None:
        mgr = FakeManager(tmp_path)
        seen: dict[str, Any] = {}

        def _produce(task: Any, path: Path) -> str:
            seen["task"] = task
            seen["path"] = path
            return "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"

        def _validate(path: Path, diff: str) -> Evidence:
            return _evidence(True)

        worker = WorktreeWorker(
            "w1", "maint", manager=mgr, produce_diff=_produce, validate=_validate,
            allowed_paths=("demo.py",),
        )
        artifact = worker.produce("sube x a 2")

        assert artifact.kind is ArtifactKind.PATCH
        assert artifact.payload["diff"].startswith("--- a/demo.py")
        assert artifact.producer_cost is CostTier.SUITE
        assert artifact.metadata["worker_id"] == "w1"
        assert artifact.metadata["allowed_paths"] == ["demo.py"]
        assert artifact.metadata["worktree_validation"]["verdict"] == "pass"
        assert seen["task"] == "sube x a 2"
        assert mgr.created == ["w1"] and mgr.torn_down == 1

    def test_teardown_runs_even_if_validation_fails(self, tmp_path: Path) -> None:
        mgr = FakeManager(tmp_path)
        worker = WorktreeWorker(
            "w1", "maint", manager=mgr,
            produce_diff=lambda t, p: "diff",
            validate=lambda p, d: _evidence(False),
        )
        artifact = worker.produce("t")
        assert artifact.metadata["worktree_validation"]["verdict"] == "fail"
        assert mgr.torn_down == 1

    def test_worker_holds_no_merkle(self, tmp_path: Path) -> None:
        # Invariante: el worker es productor puro, sin escritor de auditoría.
        worker = WorktreeWorker(
            "w1", "maint", manager=FakeManager(tmp_path),
            produce_diff=lambda t, p: "d", validate=lambda p, d: _evidence(True),
        )
        assert not hasattr(worker, "_merkle")


class TestBackendFeedsCoordinator:
    """El Artifact del worker fluye por el coordinador de capa 3 sin adaptación:
    UnifiedDiffVerifier (capa 1) lo verifica barato y aterriza en el blackboard."""

    def test_worker_artifact_lands_on_blackboard(self, tmp_path: Path) -> None:
        from datetime import datetime, timedelta, timezone

        from atlas.core.swarm import Blackboard, Envelope, SwarmCoordinator
        from atlas.core.verify import UnifiedDiffVerifier, UniversalVerifier

        diff = "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        worker = WorktreeWorker(
            "w1", "maint", manager=FakeManager(tmp_path),
            produce_diff=lambda t, p: diff, validate=lambda p, d: _evidence(True),
            allowed_paths=("demo.py",), cost=CostTier.SUITE,
        )
        coord = SwarmCoordinator(UniversalVerifier([UnifiedDiffVerifier()]), Blackboard())
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        coord.assign(worker, Envelope("w1", "maint", budget_units=100, expires_at=future))
        result = coord.run_round({"w1": "sube x a 2"})
        assert len(result.accepted) == 1
        assert result.accepted[0].artifact_kind == "patch"

    def test_out_of_scope_diff_rejected_by_coordinator(self, tmp_path: Path) -> None:
        from datetime import datetime, timedelta, timezone

        from atlas.core.swarm import Blackboard, Envelope, SwarmCoordinator
        from atlas.core.verify import UnifiedDiffVerifier, UniversalVerifier

        evil = "--- a/secrets.py\n+++ b/secrets.py\n@@ -1 +1 @@\n-a\n+b\n"
        worker = WorktreeWorker(
            "w1", "maint", manager=FakeManager(tmp_path),
            produce_diff=lambda t, p: evil, validate=lambda p, d: _evidence(True),
            allowed_paths=("demo.py",), cost=CostTier.SUITE,
        )
        coord = SwarmCoordinator(UniversalVerifier([UnifiedDiffVerifier()]), Blackboard())
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        coord.assign(worker, Envelope("w1", "maint", 100, future))
        result = coord.run_round({"w1": "t"})
        assert len(result.rejected) == 1  # tocó un path fuera de allowed_paths
