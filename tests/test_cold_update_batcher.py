"""Tests para ColdUpdateBatcher — lote de propuestas validated+self_audit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.cold_update_batcher import BatchResult, ColdUpdateBatcher
from atlas.core.cold_update_manager import ColdUpdateManager
from atlas.core.git_env import clean_git_env
from atlas.core.validation_runner import ValidationReport
from atlas.logging.merkle_logger import MerkleLogger


def _make_git_repo(tmp_path: Path, name: str = "batchproj") -> Path:
    """Repo git minimo con un commit inicial (mismo patron que test_cold_update_manager)."""
    root = tmp_path / name
    root.mkdir()
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")

    env = clean_git_env()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, env=env,
                   capture_output=True, check=True)
    return root


def _list_batch_worktrees(root: Path) -> list[str]:
    """Worktrees registrados en git cuyo nombre indica que los creo el batcher
    (prefijo 'worktree-batch-'). Los worktrees por-propuesta que crea
    ColdUpdateManager.propose() no son responsabilidad del batcher y se
    excluyen deliberadamente de esta comprobacion."""
    env = clean_git_env()
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=root, env=env, capture_output=True, text=True, check=True,
    )
    paths = [
        line.split(" ", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return [p for p in paths if "worktree-batch-" in p]


def _mgr(tmp_path: Path, root: Path, runner_factory, name: str = "b") -> ColdUpdateManager:
    ws = tmp_path / f"atlas_{name}"
    ws.mkdir(exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / f"store_{name}"
    return ColdUpdateManager(root, merkle, store_dir=store, runner_factory=runner_factory)


def _ok_report() -> ValidationReport:
    return ValidationReport(passed=True, pytest_exit=0, mypy_exit=0,
                             pytest_summary="1 passed", mypy_summary="Success")


def _fail_report() -> ValidationReport:
    return ValidationReport(passed=False, pytest_exit=1, mypy_exit=0,
                             pytest_summary="FAILED", mypy_summary="")


def _propose_validated(
    mgr: ColdUpdateManager,
    tmp_path: Path,
    name: str,
    patch_text: str,
    *,
    origin: str = "self_audit",
) -> str:
    """Propone y fuerza status=validated escribiendo directo (evita depender del
    runner_factory del manager, que el batcher reemplaza por el suyo propio)."""
    patch = tmp_path / f"{name}.patch"
    patch.write_text(patch_text, encoding="utf-8")
    proposal = mgr.propose(f"intent {name}", patch, origin=origin, risk="low")
    proposal.status = "validated"
    proposal.validation = _ok_report().to_dict()
    mgr._save()
    return proposal.id


class _ScriptedRunnerFactory:
    """runner_factory inyectable en el batcher: devuelve reports predefinidos por
    orden de llamada, o vía una funcion de decision sobre el worktree."""

    def __init__(self, decide) -> None:
        self._decide = decide

    def __call__(self, worktree: Path):
        decide = self._decide

        class _R:
            def run(self) -> ValidationReport:
                return decide(worktree)
        return _R()


def test_empty_batch_when_no_validated_proposals(tmp_path: Path) -> None:
    root = _make_git_repo(tmp_path, "empty")
    mgr = _mgr(tmp_path, root, runner_factory=lambda p: None, name="empty")
    batcher = ColdUpdateBatcher(mgr)

    result = batcher.run_batch()

    assert isinstance(result, BatchResult)
    assert result.included == []
    assert result.excluded == []
    assert result.passed is True
    assert result.pytest_summary == ""
    assert result.mypy_summary == ""
    assert result.worktree_path is None
    assert _list_batch_worktrees(root) == []


def test_two_proposals_pass_together(tmp_path: Path) -> None:
    root = _make_git_repo(tmp_path, "twopass")
    mgr = _mgr(tmp_path, root, runner_factory=lambda p: None, name="twopass")

    id_a = _propose_validated(
        mgr, tmp_path, "a",
        "--- /dev/null\n+++ b/src/atlas/a.txt\n@@ -0,0 +1 @@\n+a\n",
    )
    id_b = _propose_validated(
        mgr, tmp_path, "b",
        "--- /dev/null\n+++ b/src/atlas/b.txt\n@@ -0,0 +1 @@\n+b\n",
    )

    def factory(worktree: Path):
        return _FakeRunner(_ok_report())

    batcher = ColdUpdateBatcher(mgr, runner_factory=factory)
    result = batcher.run_batch()

    assert result.passed is True
    assert set(result.included) == {id_a, id_b}
    assert result.excluded == []
    assert result.worktree_path is None
    assert _list_batch_worktrees(root) == []

    # Persistido en batches.json
    fetched = batcher.get_batch(result.id)
    assert fetched is not None
    assert fetched.id == result.id
    assert batcher.latest_batch().id == result.id


class _FakeRunner:
    def __init__(self, report: ValidationReport) -> None:
        self._report = report

    def run(self) -> ValidationReport:
        return self._report


def test_one_proposal_breaks_combined_suite_bisected_out(tmp_path: Path) -> None:
    root = _make_git_repo(tmp_path, "bisect")
    mgr = _mgr(tmp_path, root, runner_factory=lambda p: None, name="bisect")

    id_good = _propose_validated(
        mgr, tmp_path, "good",
        "--- /dev/null\n+++ b/src/atlas/good.txt\n@@ -0,0 +1 @@\n+good\n",
    )
    id_bad = _propose_validated(
        mgr, tmp_path, "bad",
        "--- /dev/null\n+++ b/src/atlas/bad_marker.py\n@@ -0,0 +1 @@\n+BAD_MARKER = 1\n",
    )

    def decide(worktree: Path) -> ValidationReport:
        marker = worktree / "src" / "atlas" / "bad_marker.py"
        if marker.exists():
            return _fail_report()
        return _ok_report()

    factory = _ScriptedRunnerFactory(decide)
    batcher = ColdUpdateBatcher(mgr, runner_factory=factory)
    result = batcher.run_batch()

    assert result.passed is True
    assert result.included == [id_good]
    assert len(result.excluded) == 1
    assert result.excluded[0]["proposal_id"] == id_bad
    assert "rompe la suite combinada" in result.excluded[0]["reason"]
    assert _list_batch_worktrees(root) == []


def test_worktrees_cleaned_up_even_when_all_excluded(tmp_path: Path) -> None:
    root = _make_git_repo(tmp_path, "allbad")
    mgr = _mgr(tmp_path, root, runner_factory=lambda p: None, name="allbad")

    id_a = _propose_validated(
        mgr, tmp_path, "a2",
        "--- /dev/null\n+++ b/src/atlas/a2.txt\n@@ -0,0 +1 @@\n+a2\n",
    )
    id_b = _propose_validated(
        mgr, tmp_path, "b2",
        "--- /dev/null\n+++ b/src/atlas/b2.txt\n@@ -0,0 +1 @@\n+b2\n",
    )

    factory = _ScriptedRunnerFactory(lambda worktree: _fail_report())
    batcher = ColdUpdateBatcher(mgr, runner_factory=factory)
    result = batcher.run_batch()

    assert result.passed is False
    assert result.included == []
    assert {e["proposal_id"] for e in result.excluded} == {id_a, id_b}
    assert result.worktree_path is None
    assert _list_batch_worktrees(root) == []

    # Ningun directorio worktree-batch-* huerfano en disco (los worktree-<id>
    # sin 'batch' pertenecen a las propuestas individuales del manager, fuera
    # del alcance del batcher).
    leftover_batch_dirs = [
        p for p in (tmp_path / "store_allbad").glob("worktree-batch-*") if p.is_dir()
    ] if (tmp_path / "store_allbad").exists() else []
    assert leftover_batch_dirs == []


def test_get_batch_and_latest_batch_persist_across_instances(tmp_path: Path) -> None:
    root = _make_git_repo(tmp_path, "persist")
    mgr = _mgr(tmp_path, root, runner_factory=lambda p: None, name="persist")

    _propose_validated(
        mgr, tmp_path, "p1",
        "--- /dev/null\n+++ b/src/atlas/p1.txt\n@@ -0,0 +1 @@\n+p1\n",
    )

    factory = _ScriptedRunnerFactory(lambda worktree: _ok_report())
    batcher1 = ColdUpdateBatcher(mgr, runner_factory=factory)
    result1 = batcher1.run_batch()

    # Nueva instancia del batcher sobre el mismo store_dir debe ver el batch anterior.
    batcher2 = ColdUpdateBatcher(mgr, runner_factory=factory)
    fetched = batcher2.get_batch(result1.id)
    assert fetched is not None
    assert fetched.included == result1.included
    assert batcher2.latest_batch().id == result1.id


def test_batch_result_to_dict_roundtrip() -> None:
    result = BatchResult(
        id="abc",
        included=["p1"],
        excluded=[{"proposal_id": "p2", "reason": "x"}],
        passed=True,
        pytest_summary="ok",
        mypy_summary="ok",
        worktree_path=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    d = result.to_dict()
    assert d["id"] == "abc"
    assert d["included"] == ["p1"]
    assert d["excluded"] == [{"proposal_id": "p2", "reason": "x"}]
    assert d["passed"] is True
