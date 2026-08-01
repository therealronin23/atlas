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

from atlas.core.git_checkpoint import (
    GitCheckpointError,
    GitCheckpointManager,
    is_ephemeral_worktree,
)
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


class TestIsEphemeralWorktree:
    """Predicado estructural usado por el wiring agéntico (t1-git-checkpoint-
    agentic-wiring): distingue un worktree efímero real del checkout git
    principal SIN depender de una lista de rutas conocidas de antemano."""

    def test_main_checkout_is_not_a_worktree(self, real_repo: Path) -> None:
        assert (real_repo / ".git").is_dir()  # supuesto de partida real
        assert is_ephemeral_worktree(real_repo) is False

    def test_real_git_worktree_add_is_a_worktree(
        self, real_repo: Path, tmp_path: Path
    ) -> None:
        wt = tmp_path / "wt"
        _git(real_repo, "worktree", "add", "--detach", str(wt), "HEAD")
        assert (wt / ".git").is_file()  # supuesto de partida real
        assert is_ephemeral_worktree(wt) is True

    def test_non_repo_directory_is_not_a_worktree(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        assert is_ephemeral_worktree(plain) is False


class TestGpgSignIsolation:
    """2026-08-01 — absorbido de Hermes tras la auditoría comparativa: su
    checkpoint_manager fuerza GIT_CONFIG_GLOBAL/SYSTEM=/dev/null y desactiva
    gpg signing explícitamente, citando que un `commit.gpgsign=true` heredado
    dispara un prompt de pinentry GUI en cada escritura. Atlas corre como
    daemon sin terminal: ese prompt no cuelga solo esa llamada, cuelga el
    proceso entero esperando una GUI que nunca vendrá.

    Alcance deliberadamente más estrecho que Hermes: sólo se desactiva GPG
    signing vía flags de git (`-c commit.gpgsign=false`), no se anula TODO
    el config global -- las operaciones de checkpoint (stash/commit/reset/
    clean) no dependen de red ni credenciales, así que no hay necesidad de
    aislar más que el gatillo real del cuelgue."""

    def test_a_global_gpgsign_config_does_not_hang_checkpoint(
        self, real_repo: Path, manager: GitCheckpointManager, tmp_path: Path
    ) -> None:
        # commit.gpgsign=true con un signingkey inexistente falla RÁPIDO en
        # vez de colgarse (gpg real sin key -> error inmediato) -- suficiente
        # para probar que el flag de aislamiento gana sobre el config
        # heredado sin depender de un pinentry real en el entorno de test.
        fake_global = tmp_path / "fake_gitconfig_global"
        fake_global.write_text(
            "[commit]\n\tgpgsign = true\n[user]\n\tsigningkey = DEADBEEF00000000\n"
        )
        import os
        env = dict(os.environ)
        env["GIT_CONFIG_GLOBAL"] = str(fake_global)
        env["GIT_CONFIG_SYSTEM"] = "/dev/null"

        (real_repo / "file.txt").write_text("v2\n")
        import subprocess as sp
        result = sp.run(
            ["python3", "-c",
             "from pathlib import Path; from atlas.core.git_checkpoint import GitCheckpointManager; "
             f"GitCheckpointManager().checkpoint(Path({str(real_repo)!r}), run_count=1)"],
            env={**env, "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=15,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


class TestPreRollbackSafetySnapshot:
    """2026-08-01 — absorbido de Hermes: antes de CUALQUIER restore()
    destructivo, se toma un checkpoint del estado actual primero. Coste
    marginal (un stash más), beneficio real: "deshacer el deshacer" siempre
    disponible. `restore()` NO cambia su comportamiento de destino (los
    tests existentes de TestCheckpointAndRestoreEndToEnd siguen intactos) --
    esto es puramente aditivo."""

    def test_restore_leaves_a_recoverable_pre_rollback_snapshot(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        (real_repo / "file.txt").write_text("v2 (checkpoint 1)\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)

        (real_repo / "file.txt").write_text("v3 (se va a perder al restaurar)\n")
        # Sin checkpoint explícito de v3 -- es EXACTAMENTE el estado que el
        # pre-rollback snapshot debe salvar antes de que restore() lo destruya.

        pre_rollback = manager.restore(real_repo, cp1)

        assert (real_repo / "file.txt").read_text() == "v2 (checkpoint 1)\n"
        assert pre_rollback is not None, "restore() no devolvió el snapshot de seguridad"

        # Deshacer el deshacer: restaurar el pre-rollback recupera v3.
        manager.restore(real_repo, pre_rollback)
        assert (real_repo / "file.txt").read_text() == "v3 (se va a perder al restaurar)\n"

    def test_pre_rollback_snapshot_is_logged_to_merkle(
        self, real_repo: Path, tmp_path: Path
    ) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        manager = GitCheckpointManager(merkle=merkle)
        (real_repo / "file.txt").write_text("v2\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)
        (real_repo / "file.txt").write_text("v3\n")

        manager.restore(real_repo, cp1)

        entries = [e.action for e in merkle.tail(10)]
        assert "git_checkpoint.pre_rollback_snapshot" in entries


class TestNonDestructiveFileRestore:
    """2026-08-01 — absorbido de Hermes: alternativa NO destructiva a
    restore() para cuando sólo hace falta recuperar UN fichero, no todo el
    working tree. `git checkout <ref> -- <path>` en vez de reset --hard +
    clean -fd -- no borra ficheros nuevos no relacionados."""

    def test_restores_one_file_without_touching_others(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        (real_repo / "file.txt").write_text("v2 (checkpoint)\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)

        (real_repo / "file.txt").write_text("v3 (se va a deshacer)\n")
        other_new_file = real_repo / "otro_fichero_nuevo.py"
        other_new_file.write_text("esto NO debe borrarse\n")

        manager.restore_file(real_repo, cp1, "file.txt")

        assert (real_repo / "file.txt").read_text() == "v2 (checkpoint)\n"
        assert other_new_file.exists(), "restore_file() no debe tocar ficheros no pedidos"
        assert other_new_file.read_text() == "esto NO debe borrarse\n"

    def test_restore_file_logs_moderate_not_critical(
        self, real_repo: Path, tmp_path: Path
    ) -> None:
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        manager = GitCheckpointManager(merkle=merkle)
        (real_repo / "file.txt").write_text("v2\n")
        cp1 = manager.checkpoint(real_repo, run_count=1)
        (real_repo / "file.txt").write_text("v3\n")

        manager.restore_file(real_repo, cp1, "file.txt")

        entry = next(e for e in merkle.tail(10) if e.action == "git_checkpoint.restore_file")
        # Alcance de un solo fichero, no destructivo del resto del árbol --
        # menor que el "critical" de restore() completo, sigue auditado.
        assert entry.risk_level == "moderate"


class TestRetention:
    """2026-08-01 — absorbido de Hermes: cap real de retención. Atlas no
    replica el almacén compartido cross-proyecto de Hermes (violaría el
    aislamiento por worktree que es el invariante de seguridad de este
    módulo) -- pero SÍ necesita un tope dentro de la vida de un worktree:
    una tarea larga con muchos turnos puede acumular stashes sin límite."""

    def test_prune_drops_oldest_stash_checkpoints_beyond_the_cap(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        entries = []
        for i in range(5):
            (real_repo / "file.txt").write_text(f"test_v{i}\n")
            entries.append(manager.checkpoint(real_repo, run_count=i))

        dropped = manager.prune(real_repo, max_snapshots=2)

        assert dropped == 3
        remaining = _git(real_repo, "stash", "list")
        assert remaining.count("atlas-checkpoint-run-") == 2

    def test_prune_below_the_cap_is_a_noop(
        self, real_repo: Path, manager: GitCheckpointManager
    ) -> None:
        (real_repo / "file.txt").write_text("v1\n")
        manager.checkpoint(real_repo, run_count=1)

        dropped = manager.prune(real_repo, max_snapshots=20)

        assert dropped == 0


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
