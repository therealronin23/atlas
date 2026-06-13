"""
Capa 3 — worktree_validate: tests con repo git hermético en tmp_path.

REGLAS: sin red, sin GUI, sin ValidationRunner. git solo contra repos tmp
herméticos creados aquí. clean_git_env siempre presente.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.swarm_validate import worktree_validate
from atlas.core.verify import Verdict


# ---------------------------------------------------------------------------
# Helpers de repo tmp

def _clean_env() -> dict[str, str]:
    import os
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX", "GIT_COMMON_DIR"):
        env.pop(var, None)
    return env


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, env=_clean_env(), check=True,
        capture_output=True, text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo git hermético con un .py que tiene trailing whitespace."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t.t"], root)
    _git(["config", "user.name", "t"], root)
    # Fichero con whitespace al final de línea (1 espacio).
    (root / "main.py").write_text("x = 1 \ny = 2\n", encoding="utf-8")
    _git(["add", "main.py"], root)
    _git(["commit", "-qm", "init"], root)
    return root


# ---------------------------------------------------------------------------
# Utilidad: genera el diff de strip_trailing_whitespace para el repo fixture.

def _strip_diff(repo: Path) -> str:
    """Diff unificado que elimina el espacio al final de la línea 1."""
    return (
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-x = 1 \n"
        "+x = 1\n"
        " y = 2\n"
    )


# ---------------------------------------------------------------------------
# Tests

class TestWorktreeValidate:
    def test_pass_on_valid_diff(self, repo: Path) -> None:
        """Un diff correcto aplica y parsea → PASS."""
        diff = _strip_diff(repo)
        evidence = worktree_validate(repo, diff)
        assert evidence.verdict is Verdict.PASS
        assert evidence.reason == "aplica y parsea"
        assert any(c.name == "git_apply" for c in evidence.checks)
        assert any(c.name == "ast_parse" for c in evidence.checks)
        assert "worktree_validate" in evidence.verifier_ids

    def test_fail_on_empty_diff(self, repo: Path) -> None:
        """Diff vacío → FAIL honesto."""
        evidence = worktree_validate(repo, "")
        assert evidence.verdict is Verdict.FAIL
        assert "vacío" in evidence.reason

    def test_fail_on_whitespace_only_diff(self, repo: Path) -> None:
        """Diff solo espacios → FAIL honesto."""
        evidence = worktree_validate(repo, "   \n  \n")
        assert evidence.verdict is Verdict.FAIL
        assert "vacío" in evidence.reason

    def test_fail_on_garbage_diff(self, repo: Path) -> None:
        """Diff con contenido inválido que git apply rechaza → FAIL."""
        garbage = "not a diff\nthis is garbage\n"
        evidence = worktree_validate(repo, garbage)
        assert evidence.verdict is Verdict.FAIL

    def test_fail_on_diff_that_does_not_apply(self, repo: Path) -> None:
        """Diff que apunta a un fichero que no existe → FAIL."""
        bad_diff = (
            "--- a/nonexistent.py\n"
            "+++ b/nonexistent.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        evidence = worktree_validate(repo, bad_diff)
        assert evidence.verdict is Verdict.FAIL

    def test_fail_on_diff_that_breaks_ast(self, repo: Path) -> None:
        """Diff que introduce SyntaxError en un .py → FAIL."""
        # Primero aplicamos el diff limpio para que el primer diff funcione,
        # y luego verificamos un diff separado que introduce un error de sintaxis.
        # Para no depender del estado del repo después de un apply anterior,
        # usamos un repo fresco con un fichero válido y producimos un diff
        # que introduce código inválido.
        # El test trabaja sobre el mismo repo fixture; después del apply del
        # diff válido el repo ya no tiene trailing whitespace. Para este test
        # usamos una instancia de repo separada mediante tmp_path directamente.
        import tempfile, os

        tmp = Path(tempfile.mkdtemp())
        try:
            _git(["init", "-q"], tmp)
            _git(["config", "user.email", "t@t.t"], tmp)
            _git(["config", "user.name", "t"], tmp)
            (tmp / "bad.py").write_text("x = 1\n", encoding="utf-8")
            _git(["add", "bad.py"], tmp)
            _git(["commit", "-qm", "init"], tmp)

            # Diff que reemplaza 'x = 1' por código con SyntaxError.
            syntax_error_diff = (
                "--- a/bad.py\n"
                "+++ b/bad.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+def (\n"
            )
            evidence = worktree_validate(tmp, syntax_error_diff)
            assert evidence.verdict is Verdict.FAIL
            assert "AST" in evidence.reason or "rompe" in evidence.reason
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
