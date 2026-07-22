"""Structured commands are capability-scoped and OS-contained."""

from __future__ import annotations

from pathlib import Path
import shutil
from unittest.mock import MagicMock

import pytest

from atlas.governance.permission_profile import PermissionProfile
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.bwrap_jail import BwrapUnavailableError
from atlas.security.capabilities import CapabilityIssuer
from atlas.security.executor import AtlasExecutor, ExecutorError
from atlas.security.sandbox import LayeredIsolationSandbox, OperationalMode, SandboxResult
from atlas.security.ssrf_bridge import SSRFBridge


def _stack(tmp_path: Path, *, git_root: Path | None = None) -> tuple[
    PermissionProfile, CapabilityIssuer, MagicMock, AtlasExecutor, Path
]:
    workspace = tmp_path / "atlas"
    (workspace / "tmp").mkdir(parents=True)
    (workspace / "projects").mkdir()
    config = workspace / "permissions.yaml"
    config.write_text(
        "workspace:\n"
        "  auto_write:\n    - tmp/\n"
        "  confirm_write:\n    - projects/\n"
        "  read_only: []\n"
        "  read_extended: []\n"
        "telegram:\n  authorized_chat_ids: []\n"
        "shell_allowlist:\n  - echo\n  - patch\n",
        encoding="utf-8",
    )
    profile = PermissionProfile(config, workspace, git_inspect_root=git_root)
    issuer = CapabilityIssuer(profile, SSRFBridge())
    sandbox = MagicMock(spec=LayeredIsolationSandbox)
    sandbox.execute_command.return_value = SandboxResult(
        success=True,
        stdout="ok",
        stderr="",
        exit_code=0,
        duration_ms=1,
        operational_mode=OperationalMode.NORMAL,
    )
    merkle = MerkleLogger(workspace / "merkle")
    return profile, issuer, sandbox, AtlasExecutor(issuer, merkle, sandbox), workspace


def test_read_only_command_gets_no_writable_mount(tmp_path: Path) -> None:
    profile, issuer, sandbox, executor, workspace = _stack(tmp_path)
    cap = issuer.issue_exec("echo", args=("hello",), working_dir=workspace / "tmp")
    profile.mark_confirmed("exec:echo hello")

    executor.execute_exec(cap)

    sandbox.execute_command.assert_called_once_with(
        command=["echo", "hello"],
        working_dir=(workspace / "tmp").resolve(),
        timeout_s=30,
        working_dir_writable=False,
        read_only_paths=(),
    )


def test_patch_gets_only_declared_input_and_writable_cwd(tmp_path: Path) -> None:
    profile, issuer, sandbox, executor, workspace = _stack(tmp_path)
    patch_file = workspace / "tmp" / "change.patch"
    patch_file.write_text("diff", encoding="utf-8")
    args = ("-p1", "--input", str(patch_file))
    cap = issuer.issue_exec("patch", args=args, working_dir=workspace / "projects")
    profile.mark_confirmed(f"exec:patch {' '.join(args)}")

    executor.execute_exec(cap)

    sandbox.execute_command.assert_called_once_with(
        command=["patch", *args],
        working_dir=(workspace / "projects").resolve(),
        timeout_s=30,
        working_dir_writable=True,
        read_only_paths=(patch_file.resolve(),),
    )


def test_patch_never_mounts_unauthorized_input(tmp_path: Path) -> None:
    profile, issuer, sandbox, executor, workspace = _stack(tmp_path)
    args = ("--input", "/etc/passwd")
    cap = issuer.issue_exec("patch", args=args, working_dir=workspace / "projects")
    profile.mark_confirmed(f"exec:patch {' '.join(args)}")

    with pytest.raises(ExecutorError, match="entrada patch"):
        executor.execute_exec(cap)
    sandbox.execute_command.assert_not_called()


def test_git_dash_c_mounts_only_authorized_repo_read_only(tmp_path: Path) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    profile, issuer, sandbox, executor, workspace = _stack(tmp_path, git_root=repo)
    cap = issuer.issue_exec(
        "git", args=("-C", str(repo), "status"), working_dir=workspace / "tmp",
    )

    executor.execute_exec(cap)

    sandbox.execute_command.assert_called_once_with(
        command=["git", "-C", str(repo), "status"],
        working_dir=(workspace / "tmp").resolve(),
        timeout_s=30,
        working_dir_writable=False,
        read_only_paths=(repo.resolve(),),
    )


def test_executor_converts_missing_bwrap_to_fail_closed_error(tmp_path: Path) -> None:
    profile, issuer, sandbox, executor, workspace = _stack(tmp_path)
    cap = issuer.issue_exec("echo", working_dir=workspace / "tmp")
    profile.mark_confirmed("exec:echo")
    sandbox.execute_command.side_effect = BwrapUnavailableError("missing")

    with pytest.raises(ExecutorError, match="missing"):
        executor.execute_exec(cap)


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap no disponible")
def test_real_executor_patch_is_limited_to_writable_cwd(tmp_path: Path) -> None:
    profile, issuer, _mock, _executor, workspace = _stack(tmp_path)
    sandbox = LayeredIsolationSandbox(workspace)
    executor = AtlasExecutor(issuer, MerkleLogger(workspace / "real-merkle"), sandbox)
    project = workspace / "projects"
    target = project / "value.txt"
    target.write_text("before\n", encoding="utf-8")
    patch_file = workspace / "tmp" / "change.patch"
    patch_file.write_text(
        "--- value.txt\n+++ value.txt\n@@ -1 +1 @@\n-before\n+after\n",
        encoding="utf-8",
    )
    args = ("-p0", "--input", str(patch_file))
    cap = issuer.issue_exec("patch", args=args, working_dir=project)
    profile.mark_confirmed(f"exec:patch {' '.join(args)}")

    result = executor.execute_exec(cap)

    assert result.success, result.stderr
    assert target.read_text(encoding="utf-8") == "after\n"
    assert patch_file.read_text(encoding="utf-8").startswith("--- value.txt")


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap no disponible")
def test_real_executor_can_inspect_authorized_external_git_repo(tmp_path: Path) -> None:
    # Repo real y desechable, NO el propio checkout de atlas-core: usar
    # Path(__file__).resolve().parent.parent hacía que "el repo externo
    # autorizado" fuera literalmente donde vive este fichero de test — que
    # deja de ser el checkout principal cuando la suite corre copiada dentro
    # de un worktree efímero de ColdUpdate (git worktree: el .git del
    # worktree apunta a metadata FUERA del propio worktree, en
    # <repo-principal>/.git/worktrees/<nombre>, invisible para el sandbox
    # bwrap). Encontrado en vivo por F2.6 (ATLAS PRIME 2026-07-22) al validar
    # una propuesta real por la ruta dorada.
    import subprocess

    repo = tmp_path / "external_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", "--allow-empty"],
        cwd=repo,
        check=True,
    )
    profile, issuer, _mock, _executor, workspace = _stack(tmp_path, git_root=repo)
    executor = AtlasExecutor(
        issuer,
        MerkleLogger(workspace / "git-merkle"),
        LayeredIsolationSandbox(workspace),
    )
    cap = issuer.issue_exec(
        "git",
        args=("-C", str(repo), "rev-parse", "--is-inside-work-tree"),
        working_dir=workspace / "tmp",
    )

    result = executor.execute_exec(cap)

    assert result.success, result.stderr
    assert result.stdout.strip() == "true"
