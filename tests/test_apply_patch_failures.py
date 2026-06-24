"""tech-6: cobertura de fallos de git apply en ColdUpdateManager._apply_patch.

Casos cubiertos:
  - Patch válido aplicado limpiamente → archivo aparece en el worktree.
  - Patch corrupto (diff garbage) → RuntimeError explícita en propose().
  - Patch que no casa con el árbol (hunk mismatch) → RuntimeError explícita.
  - Limpieza del worktree tras fallo en _apply_patch durante propose():
      el código NO limpia el worktree en este caso → hallazgo anotado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.cold_update_manager import ColdUpdateManager
from atlas.core.git_env import clean_git_env
from atlas.logging.merkle_logger import MerkleLogger


# ---------------------------------------------------------------------------
# Fixtures compartidos
# ---------------------------------------------------------------------------

def _make_git_project(tmp_path: Path, name: str = "proj") -> Path:
    """Repo git mínimo con un commit inicial; devuelve el root."""
    root = tmp_path / name
    root.mkdir(parents=True)
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


def _mgr(root: Path, tmp_path: Path, store_suffix: str = "store") -> ColdUpdateManager:
    ws = tmp_path / f"atlas-{store_suffix}"
    ws.mkdir(parents=True, exist_ok=True)
    merkle = MerkleLogger(ws / "memory" / "audit")
    store = tmp_path / store_suffix
    return ColdUpdateManager(root, merkle, store_dir=store)


# ---------------------------------------------------------------------------
# 1. Patch válido → aplicado, archivo presente en worktree
# ---------------------------------------------------------------------------

class TestApplyPatchValid:
    def test_valid_new_file_patch_applied_to_worktree(self, tmp_path: Path) -> None:
        """Patch que crea un archivo nuevo → el archivo existe en el worktree."""
        root = _make_git_project(tmp_path, "valid_proj")
        mgr = _mgr(root, tmp_path, "valid_store")

        patch = tmp_path / "add_file.patch"
        patch.write_text(
            "--- /dev/null\n+++ b/src/atlas/new_marker.py\n"
            "@@ -0,0 +1,2 @@\n+# new marker\n+MARKER = 'applied'\n",
            encoding="utf-8",
        )

        proposal = mgr.propose("add marker file", patch)

        assert proposal.status == "proposed"
        wt = Path(proposal.worktree_path)
        applied_file = wt / "src" / "atlas" / "new_marker.py"
        assert applied_file.exists(), "El archivo del patch no fue creado en el worktree"
        content = applied_file.read_text()
        assert "MARKER = 'applied'" in content

    def test_valid_patch_modifies_existing_file(self, tmp_path: Path) -> None:
        """Patch que modifica un archivo existente → contenido actualizado en worktree."""
        root = _make_git_project(tmp_path, "mod_proj")
        mgr = _mgr(root, tmp_path, "mod_store")

        # El archivo existe en HEAD con "assert True"
        # Creamos el diff contra ese contenido exacto.
        patch = tmp_path / "modify.patch"
        patch.write_text(
            "--- a/tests/test_dummy.py\n+++ b/tests/test_dummy.py\n"
            "@@ -1,2 +1,3 @@\n def test_ok():\n     assert True\n"
            "+    # comentario añadido\n",
            encoding="utf-8",
        )

        proposal = mgr.propose("modify test_dummy", patch)

        wt = Path(proposal.worktree_path)
        content = (wt / "tests" / "test_dummy.py").read_text()
        assert "comentario añadido" in content


# ---------------------------------------------------------------------------
# 2. Patch corrupto → RuntimeError explícita, worktree se crea pero NO se borra
# ---------------------------------------------------------------------------

class TestApplyPatchCorrupt:
    def test_corrupt_patch_raises_runtime_error(self, tmp_path: Path) -> None:
        """Patch con formato inválido → RuntimeError con mensaje 'Patch no aplicable'."""
        root = _make_git_project(tmp_path, "corrupt_proj")
        mgr = _mgr(root, tmp_path, "corrupt_store")

        patch = tmp_path / "corrupt.patch"
        patch.write_text(
            "esto no es un unified diff válido\n"
            "NO HAY CABECERAS\nGARBAGE DATA\n",
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            mgr.propose("corrupt patch test", patch)

    def test_corrupt_patch_proposal_not_stored(self, tmp_path: Path) -> None:
        """Tras fallo en _apply_patch, NO se almacena ninguna propuesta."""
        root = _make_git_project(tmp_path, "nostored_proj")
        mgr = _mgr(root, tmp_path, "nostored_store")

        patch = tmp_path / "garbage.patch"
        patch.write_text("GARBAGE\n", encoding="utf-8")

        try:
            mgr.propose("bad patch", patch)
        except RuntimeError:
            pass

        assert mgr.list_proposals() == [], (
            "No debería haber propuestas almacenadas tras fallo en _apply_patch"
        )

    def test_corrupt_patch_worktree_cleaned_up(self, tmp_path: Path) -> None:
        """Tras RuntimeError en _apply_patch durante propose(), el worktree creado
        por _create_worktree debe ser eliminado — sin worktrees huérfanos en el store."""
        root = _make_git_project(tmp_path, "orphan_proj")
        store = tmp_path / "orphan_store"
        ws = tmp_path / "atlas-orphan"
        ws.mkdir(parents=True, exist_ok=True)
        merkle = MerkleLogger(ws / "memory" / "audit")
        mgr = ColdUpdateManager(root, merkle, store_dir=store)

        patch = tmp_path / "orphan.patch"
        patch.write_text("GARBAGE\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            mgr.propose("orphan wt test", patch)

        assert store.exists()
        orphaned_wts = list(store.glob("worktree-*"))
        assert orphaned_wts == [], (
            f"Worktrees huérfanos encontrados tras fallo en _apply_patch: {orphaned_wts}"
        )


# ---------------------------------------------------------------------------
# 3. Patch que no casa con el árbol (hunk mismatch)
# ---------------------------------------------------------------------------

class TestApplyPatchMismatch:
    def test_hunk_mismatch_raises_runtime_error(self, tmp_path: Path) -> None:
        """Patch con contexto que no coincide con el árbol → RuntimeError."""
        root = _make_git_project(tmp_path, "mismatch_proj")
        mgr = _mgr(root, tmp_path, "mismatch_store")

        # Este diff afirma que test_dummy.py tiene "def test_WRONG():" en línea 1,
        # pero en realidad tiene "def test_ok():". El hunk no casará.
        patch = tmp_path / "mismatch.patch"
        patch.write_text(
            "--- a/tests/test_dummy.py\n+++ b/tests/test_dummy.py\n"
            "@@ -1,2 +1,2 @@\n-def test_WRONG():\n+def test_replaced():\n"
            "     assert True\n",
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            mgr.propose("hunk mismatch test", patch)

    def test_hunk_mismatch_no_partial_changes_in_store(self, tmp_path: Path) -> None:
        """Tras hunk mismatch la propuesta no queda almacenada."""
        root = _make_git_project(tmp_path, "nop_proj")
        mgr = _mgr(root, tmp_path, "nop_store")

        patch = tmp_path / "nop.patch"
        patch.write_text(
            "--- a/tests/test_dummy.py\n+++ b/tests/test_dummy.py\n"
            "@@ -1,2 +1,2 @@\n-def test_DOES_NOT_EXIST():\n+def test_new():\n"
            "     assert True\n",
            encoding="utf-8",
        )

        try:
            mgr.propose("mismatch", patch)
        except RuntimeError:
            pass

        assert mgr.list_proposals() == []


# ---------------------------------------------------------------------------
# 4. _apply_patch en apply() (sobre root) con patch inválido
#    → RuntimeError antes de ejecutar runner; estado del root no contaminado
# ---------------------------------------------------------------------------

class TestApplyPatchOnRootFailure:
    def test_apply_patch_failure_on_root_raises(self, tmp_path: Path) -> None:
        """Si _apply_patch falla al aplicar sobre el root (en apply()), se lanza RuntimeError.

        Nota: apply() llama _apply_patch ANTES de correr el ValidationRunner.
        Si el patch no aplica sobre el root, RuntimeError de _apply_patch se propaga
        directamente (no hay rollback porque el patch nunca se aplicó).
        """
        from unittest.mock import patch as mock_patch
        from atlas.core.validation_runner import ValidationReport

        root = _make_git_project(tmp_path, "applyroot_proj")
        ok = ValidationReport(passed=True, pytest_exit=0, mypy_exit=0,
                              pytest_summary="1 passed", mypy_summary="Success")

        def fake_factory(p: Path):
            class _R:
                def run(self):
                    return ok
            return _R()

        ws = tmp_path / "atlas-applyroot"
        ws.mkdir(parents=True)
        merkle = MerkleLogger(ws / "memory" / "audit")
        store = tmp_path / "store-applyroot"
        mgr = ColdUpdateManager(root, merkle, store_dir=store, runner_factory=fake_factory)

        # Patch válido para propose() (crea archivo nuevo en worktree)
        propose_patch = tmp_path / "valid_propose.patch"
        propose_patch.write_text(
            "--- /dev/null\n+++ b/src/atlas/applyroot_marker.py\n"
            "@@ -0,0 +1 @@\n+MARKER = 1\n",
            encoding="utf-8",
        )
        proposal = mgr.propose("apply root test", propose_patch)
        mgr.validate(proposal.id)
        mgr.approve(proposal.id)

        # Ahora sobrescribimos el patch almacenado con garbage para simular
        # un patch que no aplica limpio sobre el root.
        Path(proposal.patch_path).write_text("GARBAGE PATCH CONTENT\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            mgr.apply(proposal.id)

        # El root no debería tener archivos parciales del patch (nunca se aplicó).
        assert not (root / "src" / "atlas" / "applyroot_marker.py").exists(), (
            "El root no debería tener el archivo si _apply_patch lanzó antes de crear nada"
        )
