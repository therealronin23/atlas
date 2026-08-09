"""Dos solvers sobre el mismo banco, y una fuga que había que tapar antes.

Los dos juntos valen más que por separado: **la diferencia entre ellos mide lo
que aporta el harness de Atlas**. Si un modelo desnudo puntúa más alto que
Atlas con todas sus capas, el andamio resta en vez de sumar — que es
exactamente lo que sugiere el 7,8% end-to-end y lo que nadie había comprobado.

LA FUGA. `Solver = Callable[[Path, FrozenDefect], None]` entregaba el defecto
ENTERO, y `FrozenDefect.subject` es el mensaje de commit del arreglo:

    "fix(watchdog): sabía ver «muerto», no sabía ver «vivo e inútil»"

Eso no es una pista, es la solución en prosa. Un solver que lo lea mide
comprensión lectora, no capacidad de ingeniería — el mismo vicio que hace que
el 19,78% de los "resueltos" de SWE-bench sean falsos. `fix_sha` es peor
todavía: da acceso directo al diff.

El scorer necesita ambos para montar el caso (worktree en base + test del
arreglo), así que la redacción va DESPUÉS del montaje y ANTES de llamar al
solver.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.fitness import FitnessScorer
from atlas.core.self_maintenance.frozen_defects import FrozenDefect


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
        "import sys; sys.path.insert(0, 'src')\n"
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    git("add", "-A")
    git("commit", "-q", "-m", "fix(calc): la suma restaba, sumar en vez de restar")
    return tmp_path


@pytest.fixture
def corpus(repo: Path, tmp_path: Path) -> Path:
    from dataclasses import replace

    from atlas.core.self_maintenance.frozen_defects import (
        build_candidate,
        candidate_commits,
        write_defects,
    )

    d = build_candidate(repo, candidate_commits(repo)[0])
    assert d is not None
    path = tmp_path / "corpus.jsonl"
    write_defects([replace(d, verified=True)], path)
    return path


def _runner(worktree: Path, targets: tuple[str, ...]) -> int:
    import sys

    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=worktree, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        capture_output=True, text=True, timeout=120,
    ).returncode


# --------------------------------------------------------------------------
# La fuga
# --------------------------------------------------------------------------


def test_el_solver_no_recibe_el_mensaje_del_arreglo(repo: Path, corpus: Path) -> None:
    """`subject` es la solución en prosa. Entregarlo mide otra cosa."""
    visto: list[FrozenDefect] = []

    FitnessScorer(repo, corpus, run_tests=_runner).score(
        solve=lambda w, d: visto.append(d)
    )

    assert visto
    assert visto[0].subject == ""
    assert "sumar en vez de restar" not in visto[0].subject


def test_el_solver_no_recibe_el_sha_del_arreglo(repo: Path, corpus: Path) -> None:
    """Con `fix_sha` el solver puede hacer `git show` y copiar el diff."""
    visto: list[FrozenDefect] = []

    FitnessScorer(repo, corpus, run_tests=_runner).score(
        solve=lambda w, d: visto.append(d)
    )

    assert visto[0].fix_sha == ""


def test_el_solver_no_recibe_el_parche_de_tests(repo: Path, corpus: Path) -> None:
    """El test ya está EN el worktree; entregar además el diff sólo añade
    superficie por la que filtrar contexto del commit del arreglo."""
    visto: list[FrozenDefect] = []

    FitnessScorer(repo, corpus, run_tests=_runner).score(
        solve=lambda w, d: visto.append(d)
    )

    assert visto[0].test_patch == ""


def test_lo_que_SI_recibe_basta_para_trabajar(repo: Path, corpus: Path) -> None:
    """Redactar no puede dejar al solver sin con qué: necesita saber qué tests
    tiene que poner en verde y sobre qué árbol."""
    # Las aserciones van DENTRO del solver: el worktree es efímero y a la
    # vuelta de `score()` ya está destruido.
    visto: dict[str, object] = {}

    def solve(worktree: Path, defect: FrozenDefect) -> None:
        visto["test_files"] = defect.test_files
        visto["id"] = defect.id
        visto["test_existe"] = (worktree / "tests" / "test_calc.py").is_file()
        visto["src"] = (worktree / "src" / "calc.py").read_text()

    FitnessScorer(repo, corpus, run_tests=_runner).score(solve=solve)

    assert visto["test_files"] == ("tests/test_calc.py",)
    assert visto["id"]
    assert visto["test_existe"] is True
    assert "return a - b" in str(visto["src"])


def test_la_redaccion_no_rompe_el_scoring(repo: Path, corpus: Path) -> None:
    """Un solver perfecto sigue sacando 1.0 con el defecto redactado."""

    def solve(worktree: Path, defect: FrozenDefect) -> None:
        (worktree / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    score = FitnessScorer(repo, corpus, run_tests=_runner).score(solve=solve)

    assert score.ratio == 1.0


def test_el_corpus_en_disco_conserva_todo(repo: Path, corpus: Path) -> None:
    """La redacción es para el SOLVER, no para el registro: el corpus necesita
    `fix_sha` para poder re-verificarse."""
    import json

    fila = json.loads(corpus.read_text().splitlines()[0])

    assert fila["fix_sha"]
    assert fila["subject"]
    assert fila["test_patch"]
