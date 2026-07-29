"""ColdUpdate patch-intake boundary tests.

The ColdUpdate worktree is an execution-adjacent boundary: generated, swarm,
and manual patches must be constrained before ``git apply`` or ``patch`` sees
them.  These tests deliberately exercise the real manager against tiny local
repositories; no model, network, or validation runner is involved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.cold_update_manager import ColdUpdateManager, PatchIntakeError
from atlas.core.git_env import clean_git_env
from atlas.logging.merkle_logger import MerkleLogger


def _manager(tmp_path: Path) -> tuple[Path, ColdUpdateManager, Path]:
    root = tmp_path / "project"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (root / "docs").mkdir()
    (root / "config").mkdir()
    (root / "config" / "governance.json").write_text("{}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'before'\n", encoding="utf-8"
    )

    env = clean_git_env()
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=root, env=env,
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=root, env=env, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Atlas test"],
        cwd=root, env=env, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "add", "."], cwd=root, env=env, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root, env=env, capture_output=True, check=True,
    )

    store = tmp_path / "cold-store"
    manager = ColdUpdateManager(
        root,
        MerkleLogger(tmp_path / "audit"),
        store_dir=store,
    )
    return root, manager, store


def test_accepts_explicit_dependency_manifest_root_file(tmp_path: Path) -> None:
    """ADR-039 dependency bumps retain their narrow, reviewable target."""
    _, manager, _ = _manager(tmp_path)
    patch = tmp_path / "pyproject.patch"
    patch.write_text(
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -1,2 +1,2 @@\n"
        " [project]\n"
        "-name = 'before'\n"
        "+name = 'after'\n",
        encoding="utf-8",
    )

    proposal = manager.propose("bounded dependency manifest edit", patch)

    assert proposal.status == "proposed"
    assert "name = 'after'" in (
        Path(proposal.worktree_path) / "pyproject.toml"
    ).read_text(encoding="utf-8")


def test_accepts_normal_git_new_file_diff_inside_allowed_scope(tmp_path: Path) -> None:
    """Real ``git diff`` metadata stays within the supported text subset."""
    root, manager, _ = _manager(tmp_path)
    created = root / "src" / "atlas" / "generated.py"
    created.write_text("GENERATED = True\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", "src/atlas/generated.py"],
        cwd=root,
        env=clean_git_env(),
        capture_output=True,
        check=True,
    )
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=root,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0
    assert diff.stdout.startswith("diff --git a/src/atlas/generated.py")
    patch = tmp_path / "new-file.patch"
    patch.write_text(diff.stdout, encoding="utf-8")

    proposal = manager.propose("allowed new file", patch)

    assert (Path(proposal.worktree_path) / "src" / "atlas" / "generated.py").read_text(
        encoding="utf-8"
    ) == "GENERATED = True\n"


@pytest.mark.parametrize(
    ("name", "patch_text", "message"),
    [
        (
            "governance",
            "--- a/config/governance.json\n"
            "+++ b/config/governance.json\n"
            "@@ -1 +1 @@\n-{}\n+{\"changed\": true}\n",
            "governance",
        ),
        (
            "outside-prefix",
            "--- a/README.md\n+++ b/README.md\n"
            "@@ -1 +1 @@\n-before\n+after\n",
            "allowlist",
        ),
        (
            "traversal",
            "--- a/src/atlas/../../config/governance.json\n"
            "+++ b/src/atlas/../../config/governance.json\n"
            "@@ -1 +1 @@\n-before\n+after\n",
            "segmento inseguro",
        ),
        (
            "git-metadata",
            "--- a/.git/config\n+++ b/.git/config\n"
            "@@ -1 +1 @@\n-before\n+after\n",
            "allowlist",
        ),
    ],
)
def test_rejects_disallowed_paths_before_creating_worktree(
    tmp_path: Path,
    name: str,
    patch_text: str,
    message: str,
) -> None:
    _, manager, store = _manager(tmp_path)
    patch = tmp_path / f"{name}.patch"
    patch.write_text(patch_text, encoding="utf-8")

    with pytest.raises(PatchIntakeError, match=message):
        manager.propose("untrusted path", patch, origin="self_audit", risk="high")

    assert manager.list_proposals() == []
    assert list(store.glob("worktree-*")) == []
    assert list(store.glob("patch-*.patch")) == []


def test_rejects_unsafe_path_hidden_in_git_header(tmp_path: Path) -> None:
    """All path-bearing headers are checked, not only ---/+++ headers."""
    _, manager, store = _manager(tmp_path)
    patch = tmp_path / "hidden-path.patch"
    patch.write_text(
        "diff --git a/src/atlas/safe.py b/../../outside.py\n"
        "--- a/src/atlas/safe.py\n"
        "+++ b/src/atlas/safe.py\n"
        "@@ -0,0 +1 @@\n"
        "+safe = True\n",
        encoding="utf-8",
    )

    with pytest.raises(PatchIntakeError, match="segmento inseguro"):
        manager.propose("hidden traversal", patch)

    assert manager.list_proposals() == []
    assert list(store.glob("worktree-*")) == []


def test_revalidates_stored_patch_before_root_apply(tmp_path: Path) -> None:
    """A proposal file modified after review cannot bypass the intake gate."""
    root, manager, _ = _manager(tmp_path)
    patch = tmp_path / "safe.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/safe.py\n"
        "@@ -0,0 +1 @@\n+safe = True\n",
        encoding="utf-8",
    )
    proposal = manager.propose("safe candidate", patch)
    proposal.status = "approved"  # Exercise apply's intake re-check directly.
    Path(proposal.patch_path).write_text(
        "--- a/config/governance.json\n"
        "+++ b/config/governance.json\n"
        "@@ -1 +1 @@\n-{}\n+{\"changed\": true}\n",
        encoding="utf-8",
    )

    with pytest.raises(PatchIntakeError, match="governance"):
        manager.apply(proposal.id)

    assert not (root / "src" / "atlas" / "safe.py").exists()
    assert (root / "config" / "governance.json").read_text(encoding="utf-8") == "{}\n"


def test_rejects_changed_but_in_scope_patch_before_root_apply(tmp_path: Path) -> None:
    """Approval is bound to bytes, not merely to a still-allowed path."""
    root, manager, _ = _manager(tmp_path)
    patch = tmp_path / "safe.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/safe.py\n"
        "@@ -0,0 +1 @@\n+safe = True\n",
        encoding="utf-8",
    )
    proposal = manager.propose("safe candidate", patch)
    proposal.status = "approved"
    Path(proposal.patch_path).write_text(
        "--- /dev/null\n+++ b/src/atlas/different.py\n"
        "@@ -0,0 +1 @@\n+different = True\n",
        encoding="utf-8",
    )

    with pytest.raises(PatchIntakeError, match="digest"):
        manager.apply(proposal.id)

    assert not (root / "src" / "atlas" / "safe.py").exists()
    assert not (root / "src" / "atlas" / "different.py").exists()


def test_legacy_proposal_without_digest_fails_closed(tmp_path: Path) -> None:
    """An old ledger entry cannot inherit approval for unverifiable bytes."""
    root, manager, _ = _manager(tmp_path)
    patch = tmp_path / "safe.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/src/atlas/safe.py\n"
        "@@ -0,0 +1 @@\n+safe = True\n",
        encoding="utf-8",
    )
    proposal = manager.propose("legacy candidate", patch)
    proposal.status = "approved"
    proposal.patch_sha256 = ""

    with pytest.raises(PatchIntakeError, match="sin digest"):
        manager.apply(proposal.id)

    assert not (root / "src" / "atlas" / "safe.py").exists()
