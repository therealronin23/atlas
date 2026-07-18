"""
Tests del Git Checkpoint Manager (absorbido de Cline, 2026-07-18).

Repo git REAL en tmp_path (no mocks) — para algo destructivo (reset --hard +
clean -fd), quiero probar el mecanismo de restauración de extremo a extremo,
no solo que se llame a subprocess con los argumentos correctos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.git_checkpoint import GitCheckpointError, GitCheckpointManager
from atlas.logging.merkle_logger import MerkleLogger


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def real_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@atlas.local")
    _git(repo, "config", "user.name", "atlas-test")
    (repo / "file.txt").write_text("v1\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


@pytest.fixture
def manager() -> GitCheckpointManager:
    return GitCheckpointManager()


class TestVerification:
    def test_non_git_directory_raises(self, tmp_path: Path, manager: GitCheckpointManager) -> None:
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()
        with pytest.raises(GitCheckpointError, match="no es un repo git"):
            manager.checkpoint(not_a_repo, run_count=1)

    def test_missing_directory_raises(self, tmp_path: Path, manager: GitCheckpointManager) -> None:
        with pytest.raises(GitCheckpointError, match="no existe"):
            manager.checkpoint(tmp_path / "no-existe", run_count=1)


class TestCheckpointAndRestoreEndToEnd:
    def test_restores_tracked_file_to_earlier_state(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        (real_repo / "file.txt").write_text("v2 (turno 1 del agente)\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)

        (real_repo / "file.txt").write_text("v3 (turno 2 del agente, se va a deshacer)\n")
        manager.checkpoint(real_repo, run_count=2)

        manager.restore(real_repo, cp1)

        assert (real_repo / "file.txt").read_text() == "v2 (turno 1 del agente)\n"

    def test_restore_removes_untracked_files_created_after_checkpoint(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        cp1 = manager.checkpoint(real_repo, run_count=1)

        new_file = real_repo / "nuevo_del_agente.py"
        new_file.write_text("cosa que el agente creó en el turno 2\n")
        manager.checkpoint(real_repo, run_count=2)
        assert new_file.exists()

        manager.restore(real_repo, cp1)

        assert not new_file.exists()  # git clean -fd lo borra

    def test_checkpoint_does_not_lose_working_tree_state(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        # checkpoint() debe dejar el working tree EXACTAMENTE como estaba
        # (stash + apply inmediato) — el agente sigue trabajando sin notar
        # que se grabó un checkpoint por debajo.
        (real_repo / "file.txt").write_text("estado en progreso\n")
        manager.checkpoint(real_repo, run_count=1)
        assert (real_repo / "file.txt").read_text() == "estado en progreso\n"

    def test_restore_to_invalid_ref_raises_not_crashes_silently(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        from atlas.core.git_checkpoint import CheckpointEntry

        fake = CheckpointEntry(
            ref="0000000000000000000000000000000000000000",
            run_count=1, kind="stash", created_at="2026-01-01T00:00:00+00:00",
        )
        with pytest.raises(GitCheckpointError):
            manager.restore(real_repo, fake)


class TestMerkleAudit:
    def test_checkpoint_logs_safe_restore_logs_critical(
        self, real_repo: Path, tmp_path: Path
    ) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        manager = GitCheckpointManager(merkle=merkle)

        (real_repo / "file.txt").write_text("v2\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)
        manager.restore(real_repo, cp1)

        entries = list(merkle.tail(10))
        checkpoint_entry = next(e for e in entries if e.action == "git_checkpoint.checkpoint")
        restore_entry = next(e for e in entries if e.action == "git_checkpoint.restore")
        assert checkpoint_entry.risk_level == "safe"
        assert restore_entry.risk_level == "critical"  # destructivo, debe quedar marcado alto
