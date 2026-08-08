"""Verificación: convertir 20 candidatos en un benchmark, o en menos.

Un candidato cosechado NO es un defecto todavía. Sólo lo es si su test FALLA en
`base_sha` y PASA en `fix_sha`. Un commit `fix(` puede tocar tests por otra
razón (renombrar, mover, endurecer un caso ya verde); esos miden cero y hay que
sacarlos del corpus, porque inflan el denominador del score y harían parecer
que el lazo empeora.

Por qué NO se reutiliza `EngineeringReproductionRunner`, que sería lo obvio: por
diseño **nunca aplica un parche** ("it never applies a patch, starts a provider,
creates a Task, or persists output"). Es una frontera de seguridad deliberada y
debilitarla para medir sería un mal negocio. Aquí hace falta la combinación
código-en-base + test-del-arreglo, que es justo lo que ese runner prohíbe.

La vía que no toca esa frontera: worktree en `base_sha` y
`git checkout <fix_sha> -- <test_files>`. Es estrictamente más seguro que
aplicar un diff arbitrario — sólo puede traer ficheros de un commit inmutable
del mismo repositorio, no contenido inventado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from atlas.core.self_maintenance.frozen_defects import (
    FrozenDefect,
    build_candidate,
    candidate_commits,
    verify_defect,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
        "PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
    }

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True,
                       capture_output=True)

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "feat: calculadora")
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    git("add", "-A")
    git("commit", "-q", "-m", "fix(calc): la suma restaba")
    return tmp_path


@pytest.fixture
def defect(repo: Path) -> FrozenDefect:
    d = build_candidate(repo, candidate_commits(repo)[0])
    assert d is not None
    return d


class _Runner:
    """Ejecutor inyectable: (worktree, targets) -> exit code."""

    def __init__(self, *exits: int) -> None:
        self.exits = list(exits)
        self.calls: list[tuple[Path, tuple[str, ...]]] = []

    def __call__(self, worktree: Path, targets: tuple[str, ...]) -> int:
        self.calls.append((worktree, targets))
        return self.exits.pop(0) if self.exits else 0


# --------------------------------------------------------------------------
# El criterio
# --------------------------------------------------------------------------


def test_falla_en_base_y_pasa_en_fix_es_verificado(
    repo: Path, defect: FrozenDefect
) -> None:
    outcome = verify_defect(repo, defect, run_tests=_Runner(1, 0))

    assert outcome.verified is True
    assert outcome.fails_at_base is True
    assert outcome.passes_at_fix is True


def test_si_ya_pasa_en_base_no_es_defecto(repo: Path, defect: FrozenDefect) -> None:
    """El falso positivo de la cosecha: el commit tocó tests por otra razón."""
    outcome = verify_defect(repo, defect, run_tests=_Runner(0, 0))

    assert outcome.verified is False
    assert outcome.fails_at_base is False
    assert "base" in outcome.reason.lower()


def test_si_no_pasa_ni_con_el_arreglo_se_descarta(
    repo: Path, defect: FrozenDefect
) -> None:
    """Un test que falla en los dos lados mide el entorno, no el arreglo."""
    outcome = verify_defect(repo, defect, run_tests=_Runner(1, 1))

    assert outcome.verified is False
    assert outcome.passes_at_fix is False


def test_no_se_ejecuta_en_fix_si_ya_falla_el_criterio_de_base(
    repo: Path, defect: FrozenDefect
) -> None:
    """Corte barato: si pasa en base ya está descartado, y la segunda ejecución
    cuesta lo mismo que la primera."""
    runner = _Runner(0)

    verify_defect(repo, defect, run_tests=runner)

    assert len(runner.calls) == 1


# --------------------------------------------------------------------------
# El montaje del worktree
# --------------------------------------------------------------------------


def test_el_test_del_arreglo_llega_al_worktree_de_base(
    repo: Path, defect: FrozenDefect
) -> None:
    """El núcleo del método: código viejo, test nuevo. Sin esto la verificación
    corre el test ANTIGUO (o ninguno) y no mide nada."""
    # Hay DOS ejecuciones (base y fix); esta comprobación es sobre la PRIMERA.
    vistos: list[dict[str, Any]] = []

    def runner(worktree: Path, targets: tuple[str, ...]) -> int:
        vistos.append({
            "test_existe": (worktree / "tests" / "test_calc.py").is_file(),
            "src": (worktree / "src" / "calc.py").read_text(),
        })
        return 1 if len(vistos) == 1 else 0

    verify_defect(repo, defect, run_tests=runner)

    base = vistos[0]
    assert base["test_existe"] is True, "el test del arreglo no llegó al worktree"
    assert "return a - b" in base["src"], "el src en base NO puede ser el arreglado"
    # Y la segunda sí corre sobre el arreglo, que es la otra mitad del criterio.
    assert "return a + b" in vistos[1]["src"]


def test_el_worktree_no_es_el_repo(repo: Path, defect: FrozenDefect) -> None:
    """Verificar no puede tocar el checkout vivo del operador."""
    rutas: list[Path] = []

    def runner(worktree: Path, targets: tuple[str, ...]) -> int:
        rutas.append(worktree.resolve())
        return 1

    verify_defect(repo, defect, run_tests=runner)

    assert all(p != repo.resolve() for p in rutas)


def test_los_worktrees_se_limpian(repo: Path, defect: FrozenDefect) -> None:
    """20 defectos x 2 ejecuciones = 40 worktrees fugados si no se barren; este
    repo ya tuvo 15 huérfanos por esa vía."""
    rutas: list[Path] = []

    def runner(worktree: Path, targets: tuple[str, ...]) -> int:
        rutas.append(worktree.resolve())
        return 1

    verify_defect(repo, defect, run_tests=runner)

    assert rutas
    assert all(not p.exists() for p in rutas)


def test_los_targets_son_los_ficheros_del_defecto(
    repo: Path, defect: FrozenDefect
) -> None:
    runner = _Runner(1, 0)

    verify_defect(repo, defect, run_tests=runner)

    assert runner.calls[0][1] == defect.test_files


# --------------------------------------------------------------------------
# Fail-honesto
# --------------------------------------------------------------------------


def test_un_sha_inexistente_no_revienta(repo: Path, defect: FrozenDefect) -> None:
    roto = FrozenDefect(**{**defect.to_dict(), "base_sha": "0" * 40,
                           "test_files": tuple(defect.test_files)})

    outcome = verify_defect(repo, roto, run_tests=_Runner(1, 0))

    assert outcome.verified is False
    assert outcome.reason


def test_un_ejecutor_que_lanza_no_tumba_la_verificacion(
    repo: Path, defect: FrozenDefect
) -> None:
    """Verificar 20 defectos no puede caerse entero por uno malo."""

    def runner(worktree: Path, targets: tuple[str, ...]) -> int:
        raise OSError("pytest no arrancó")

    outcome = verify_defect(repo, defect, run_tests=runner)

    assert outcome.verified is False
    assert "OSError" in outcome.reason


def test_el_resultado_es_serializable(repo: Path, defect: FrozenDefect) -> None:
    import json

    outcome = verify_defect(repo, defect, run_tests=_Runner(1, 0))

    assert json.loads(json.dumps(outcome.to_dict()))["defect_id"] == defect.id
