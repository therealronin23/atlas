"""`OracleSolver`: el control que hace creíble un cero.

Medido el 2026-08-10 sobre 5 defectos reales, con 3 tiradas cada uno:
`baseline 0/5`, `atlas_toolcoder 0/5`. Un cero admite DOS lecturas
incompatibles —"los solvers no pueden" o "el banco es imposible de superar"— y
elegir entre ellas es todo el valor del número.

Los extremos del instrumento estaban validados (`test_fitness_scorer.py`), pero
sobre un repositorio de juguete de un solo defecto sintético. El docstring de
`fitness.py` afirmaba "un solver que aplica el arreglo real -> 19/19" y **eso
nunca se había ejecutado**: exactamente la clase de afirmación sin respaldo que
esta auditoría persigue.

`OracleSolver` hace trampa a propósito: trae el arreglo real del commit. Su
resultado no es un competidor, es la cota superior del banco. Si el oráculo no
saca N/N, el problema está en el banco y ningún otro número de ese pase
significa nada.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.fitness import FitnessScorer, _redact
from atlas.core.self_maintenance.fitness_solvers import OracleSolver
from atlas.core.self_maintenance.frozen_defects import FrozenDefect

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
    "PATH": "/usr/bin:/bin",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    env = {**_ENV, "HOME": str(tmp_path)}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True,
                       capture_output=True)

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "feat: calculadora")
    # El arreglo toca código Y test: el oráculo debe traer sólo el código.
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "src" / "nuevo.py").write_text("VALOR = 1\n")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "import sys; sys.path.insert(0, 'src')\n"
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    git("add", "-A")
    git("commit", "-q", "-m", "fix(calc): la suma restaba")
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


def _pytest_runner(worktree: Path, targets: tuple[str, ...]) -> int:
    import sys

    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=worktree,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        capture_output=True, text=True, timeout=120,
    ).returncode


# --------------------------------------------------------------------------
# La cota superior
# --------------------------------------------------------------------------


def test_el_oraculo_saca_todo_sobre_el_corpus(repo: Path, corpus: Path) -> None:
    """Si esto no da 1.0, el banco es imposible y sus ceros no significan nada."""
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)

    score = scorer.score(solve=OracleSolver(repo, scorer.defects()))

    assert score.solved == score.total == 1
    assert score.ratio == 1.0


def test_el_oraculo_trae_los_ficheros_nuevos_del_arreglo(
    repo: Path, corpus: Path
) -> None:
    """Un arreglo que AÑADE un módulo no se aplica con un checkout de ficheros
    ya existentes; `git checkout <sha> -- <ruta>` sí lo trae."""
    visto: dict[str, bool] = {}
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)
    oraculo = OracleSolver(repo, scorer.defects())

    def solve(worktree: Path, defect: FrozenDefect) -> None:
        oraculo(worktree, defect)
        visto["nuevo"] = (worktree / "src" / "nuevo.py").exists()

    scorer.score(solve=solve)

    assert visto["nuevo"]


def test_el_oraculo_no_reescribe_el_examen(repo: Path, corpus: Path) -> None:
    """Traer los tests del arreglo sería innecesario (el montaje ya los puso) y
    peligroso: abriría la puerta a que un arreglo que relajó un test se cuele
    como resuelto."""
    visto: dict[str, str] = {}
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)
    oraculo = OracleSolver(repo, scorer.defects())

    def solve(worktree: Path, defect: FrozenDefect) -> None:
        (worktree / "tests" / "test_calc.py").write_text("CENTINELA\n")
        oraculo(worktree, defect)
        visto["tests"] = (worktree / "tests" / "test_calc.py").read_text()

    scorer.score(solve=solve)

    assert visto["tests"] == "CENTINELA\n"


# --------------------------------------------------------------------------
# Un oráculo roto tiene que gritar, no puntuar cero
# --------------------------------------------------------------------------


def test_sin_defectos_no_se_puede_construir(repo: Path) -> None:
    """Un oráculo vacío puntuaría 0 y se leería como "el banco es imposible".
    Ese es justo el diagnóstico invertido que este control existe para evitar."""
    with pytest.raises(ValueError, match="sin fix_sha"):
        OracleSolver(repo, [])


def test_un_defecto_desconocido_lanza(repo: Path, corpus: Path) -> None:
    """`score()` lo registrará como `reason`, no como un fallo silencioso."""
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)
    conocido = scorer.defects()[0]
    oraculo = OracleSolver(repo, [conocido])

    from dataclasses import replace

    with pytest.raises(KeyError):
        oraculo(repo, replace(conocido, id="0000000000ff"))


def test_el_oraculo_no_depende_del_defecto_redactado(
    repo: Path, corpus: Path
) -> None:
    """El scorer redacta `fix_sha` antes de llamar al solver — por diseño. El
    oráculo lo resuelve por `id` contra el corpus sin redactar, así que sigue
    funcionando con lo que realmente recibe."""
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)
    defecto = scorer.defects()[0]
    oraculo = OracleSolver(repo, [defecto])

    redactado = _redact(defecto)
    assert redactado.fix_sha == ""

    score = scorer.score(solve=oraculo)
    assert score.solved == 1


# --------------------------------------------------------------------------
# Dos pases a la vez no pueden falsearse el número
# --------------------------------------------------------------------------


def test_dos_pases_no_chocan_de_worktree(repo: Path, corpus: Path) -> None:
    """Detectado el 2026-08-10 al querer correr el control MIENTRAS corría la
    medición: ambos pases nombraban el worktree `fitness-score-<id>`, el segundo
    `git worktree add` habría fallado sobre un path existente, y `score()` lo
    habría anotado como defecto NO resuelto. Un cero que mide al vecino, no al
    solver — un error disfrazado de estado normal, otra vez."""
    nombres: list[str] = []

    def anotar(worktree: Path, defect: FrozenDefect) -> None:
        nombres.append(worktree.name)

    for _ in range(2):
        FitnessScorer(repo, corpus, run_tests=_pytest_runner).score(solve=anotar)

    assert len(nombres) == 2
    assert nombres[0] != nombres[1], "dos pases reutilizan el mismo path"
    assert all(n.startswith("fitness-score-") for n in nombres), "nombre no rastreable"


def test_un_worktree_huerfano_no_produce_un_cero_falso(
    repo: Path, corpus: Path
) -> None:
    """El leak de worktrees del 2026-07-09 dejó 15 restos. Uno solo bastaría
    para envenenar todos los pases siguientes del mismo defecto."""
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)
    huerfano = repo / ".atlas-worktrees" / f"fitness-score-{scorer.defects()[0].id}"
    huerfano.mkdir(parents=True)
    (huerfano / "basura.txt").write_text("resto de un pase muerto\n")

    score = scorer.score(solve=OracleSolver(repo, scorer.defects()))

    assert score.solved == 1, [o.get("reason") for o in score.outcomes]


def test_el_oraculo_no_es_un_competidor() -> None:
    """Salvaguarda de lectura: si alguien lo mete en la tabla de comparación, el
    "aporte del harness" saldría negativo contra un solver que hace trampa."""
    import inspect

    from atlas.core.self_maintenance import fitness_solvers

    doc = inspect.getdoc(fitness_solvers.OracleSolver) or ""
    assert "control" in doc.lower()
    assert "cota superior" in doc.lower()
