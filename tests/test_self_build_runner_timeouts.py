"""
Frontera del lazo autónomo: correr tests de un candidato (2026-08-05).

`_evaluate_candidate_in_worktree` escribe un candidato en un worktree efímero
y corre `test_cmd` para puntuarlo. Se lanzaba **sin `timeout=`** — y el fichero
entero no tenía ni uno en sus 8 subprocesos.

Por qué importa más aquí que en otros sitios: esto es el lazo de EVOLUCIÓN, el
que corre desatendido. `test_cmd` sale del backlog, así que un item mal escrito
—o un candidato generado que mete un bucle infinito, que es literalmente lo que
se está evaluando— cuelga la autoconstrucción para siempre, sin nadie mirando y
sin dejar rastro de por qué se paró.

El manejo de error ya existía y era correcto: `except (OSError,
SubprocessError)` puntúa 0.0 fail-closed, y `TimeoutExpired` hereda de
`SubprocessError`. Sólo faltaba que el cuelgue pudiera convertirse en error
alguna vez.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.core.self_maintenance.self_build_runner import (
    CANDIDATE_TEST_TIMEOUT_S,
    SelfBuildRunner,
)


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@atlas.local")
    _git(root, "config", "user.name", "atlas-test")
    (root / "target.py").write_text("x = 1\n")
    _git(root, "add", "target.py")
    _git(root, "commit", "-q", "-m", "initial")
    return root


class TestAHangingCandidateDoesNotHangTheLoop:
    def test_a_test_cmd_that_never_returns_scores_zero(self, repo: Path) -> None:
        """Prueba REAL con un proceso que de verdad no vuelve, no un mock: es
        el único modo de saber que el tope llega al subproceso."""
        runner = SelfBuildRunner(
            repo_root=repo, hub=MagicMock(), cold_update_manager=MagicMock(),
            candidate_test_timeout_s=2.0,
        )

        result = runner._evaluate_candidate_in_worktree(
            target_rel="target.py",
            candidate_code="x = 2\n",
            test_cmd=[sys.executable, "-c", "import time; time.sleep(60)"],
            base_ref="HEAD",
        )

        # fail-closed: un candidato que no se puede evaluar NO puntúa alto.
        assert result == {"score": 0.0}

    def test_a_fast_passing_candidate_still_scores_one(self, repo: Path) -> None:
        """El tope no puede romper el camino bueno."""
        runner = SelfBuildRunner(
            repo_root=repo, hub=MagicMock(), cold_update_manager=MagicMock(),
            candidate_test_timeout_s=30.0,
        )

        result = runner._evaluate_candidate_in_worktree(
            target_rel="target.py",
            candidate_code="x = 2\n",
            test_cmd=[sys.executable, "-c", "raise SystemExit(0)"],
            base_ref="HEAD",
        )

        assert result == {"score": 1.0}

    def test_the_worktree_is_cleaned_up_even_after_a_timeout(self, repo: Path) -> None:
        """Un cuelgue no puede dejar worktrees huérfanos: ya hubo una fuga de
        15 por esa vía (2026-07-09) y el `finally` existe justo por eso."""
        runner = SelfBuildRunner(
            repo_root=repo, hub=MagicMock(), cold_update_manager=MagicMock(),
            candidate_test_timeout_s=2.0,
        )

        runner._evaluate_candidate_in_worktree(
            target_rel="target.py",
            candidate_code="x = 2\n",
            test_cmd=[sys.executable, "-c", "import time; time.sleep(60)"],
            base_ref="HEAD",
        )

        listing = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list"],
            capture_output=True, text=True,
        ).stdout
        assert "self-build-evo-" not in listing


class TestTheDefaultIsGenerousEnoughForARealSuite:
    def test_default_leaves_room_for_a_real_test_command(self) -> None:
        """Un tope corto convertiría suites legítimas en candidatos
        descartados, que es peor que no tenerlo: el lazo aprendería que todo
        falla. La suite completa de este repo tarda ~7 min."""
        assert CANDIDATE_TEST_TIMEOUT_S >= 900
