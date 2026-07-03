"""
Tests de verificación — técnica #16 (Aider auto-commit): commitear cambios de
AtlasCoder automáticamente tras un éxito, con mensaje generado + chequeo de
autoría para /undo seguro (patrón Aider, mensaje por modelo barato quedó fuera
de alcance — usamos un mensaje determinista con la tarea).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from atlas.core.git_autocommit import commit_changes, is_atlas_commit


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "foo.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def test_commit_changes_creates_commit(tmp_path: Path):
    repo = _git_repo(tmp_path)
    (repo / "foo.py").write_text("x = 2\n")

    sha = commit_changes(repo, files_changed=["foo.py"], task="cambia x")
    assert sha is not None

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "cambia x" in log


def test_commit_changes_no_files_returns_none(tmp_path: Path):
    repo = _git_repo(tmp_path)
    sha = commit_changes(repo, files_changed=[], task="nada que commitear")
    assert sha is None


def test_is_atlas_commit_true_for_own_commit(tmp_path: Path):
    repo = _git_repo(tmp_path)
    (repo / "foo.py").write_text("x = 3\n")
    sha = commit_changes(repo, files_changed=["foo.py"], task="otro cambio")
    assert sha is not None
    assert is_atlas_commit(repo, sha) is True


def test_is_atlas_commit_false_for_human_commit(tmp_path: Path):
    repo = _git_repo(tmp_path)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert is_atlas_commit(repo, head_sha) is False
