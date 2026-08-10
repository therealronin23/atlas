"""FitnessScorer: el número que el lazo tiene que subir.

El denominador ya existe — 19 defectos verificados en
`docs/fixtures/fitness/frozen_defects.jsonl`, cada uno comprobado ejecutando
que falla en su base y pasa con su arreglo. Falta el numerador.

La forma es la de `benchmark_gate.py`, que ya existe y `ColdUpdateBatcher` ya
sabe consumir: dataclass de resultado con `to_dict()`, runner inyectable, una
entrada. No se inventa un patrón nuevo.

La diferencia con `BenchmarkGate` es lo que mide, y es toda la diferencia:
`BenchmarkGate` compara antes/después y responde "¿he empeorado?" — una
RESTRICCIÓN más, como pytest. `FitnessScorer` responde "¿cuánto resuelvo?", que
es lo único que puede subir.

VALIDACIÓN DEL PROPIO INSTRUMENTO, que es lo que lo hace creíble:
  - un solver que no hace nada           -> 0.0
  - un solver que aplica el arreglo real -> 1.0
Si esas dos no se cumplen, la métrica no mide nada y cualquier número
intermedio sería ruido.

Aquí se fijan sobre un repositorio SINTÉTICO de un defecto, que es lo que un
test unitario puede permitirse. La versión sobre el corpus real vive en
`test_fitness_oracle.py` y la ejecuta `fitness_run.py` en cada pase: este
fichero decía "-> 19/19" y esa ejecución nunca había ocurrido.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.fitness import FitnessScore, FitnessScorer


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
    git("commit", "-q", "-m", "fix(calc): la suma restaba")
    return tmp_path


@pytest.fixture
def corpus(repo: Path, tmp_path: Path) -> Path:
    from atlas.core.self_maintenance.frozen_defects import (
        build_candidate,
        candidate_commits,
        write_defects,
    )
    from dataclasses import replace

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
# Validación del instrumento — los dos extremos
# --------------------------------------------------------------------------


def test_solver_nulo_saca_cero(repo: Path, corpus: Path) -> None:
    """Sin arreglar nada, todos los defectos siguen fallando. Un scorer que
    diera >0 aquí estaría midiendo otra cosa."""
    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)

    score = scorer.score(solve=lambda worktree, defect: None)

    assert score.total == 1
    assert score.solved == 0
    assert score.ratio == 0.0


def test_solver_perfecto_saca_todo(repo: Path, corpus: Path) -> None:
    """Aplicando el arreglo real se resuelven todos. Si esto no diera 1.0, el
    banco sería imposible de superar y el número no significaría nada."""

    def solve(worktree: Path, defect: object) -> None:
        (worktree / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    scorer = FitnessScorer(repo, corpus, run_tests=_pytest_runner)

    score = scorer.score(solve=solve)

    assert score.solved == 1
    assert score.ratio == 1.0


# --------------------------------------------------------------------------
# Contrato
# --------------------------------------------------------------------------


def test_solo_cuentan_los_verificados(repo: Path, tmp_path: Path) -> None:
    """Un candidato sin verificar infla el denominador y hace parecer que el
    lazo empeora sin haber cambiado nada."""
    from atlas.core.self_maintenance.frozen_defects import (
        build_candidate,
        candidate_commits,
        write_defects,
    )

    d = build_candidate(repo, candidate_commits(repo)[0])
    assert d is not None
    path = tmp_path / "sin_verificar.jsonl"
    write_defects([d], path)  # verified=False por defecto

    score = FitnessScorer(repo, path, run_tests=_pytest_runner).score(
        solve=lambda w, x: None
    )

    assert score.total == 0
    assert score.ratio == 0.0


def test_el_solver_no_ve_el_arreglo(repo: Path, corpus: Path) -> None:
    """Lo que hace no-hackeable la métrica: el worktree tiene el código EN BASE
    y el test del arreglo, nunca el diff de la solución."""
    visto: dict[str, str] = {}

    def solve(worktree: Path, defect: object) -> None:
        visto["src"] = (worktree / "src" / "calc.py").read_text()
        visto["tests"] = str(sorted(p.name for p in (worktree / "tests").iterdir()))

    FitnessScorer(repo, corpus, run_tests=_pytest_runner).score(solve=solve)

    assert "return a - b" in visto["src"], "el solver está viendo el arreglo"
    assert "test_calc.py" in visto["tests"], "el solver no ve el test que debe pasar"


def test_un_solver_que_revienta_no_tumba_el_pase(repo: Path, corpus: Path) -> None:
    """Puntuar 19 defectos no puede caerse por uno malo."""

    def solve(worktree: Path, defect: object) -> None:
        raise RuntimeError("el solver explotó")

    score = FitnessScorer(repo, corpus, run_tests=_pytest_runner).score(solve=solve)

    assert score.total == 1
    assert score.solved == 0
    assert any("RuntimeError" in o.get("reason", "") for o in score.outcomes)


def test_no_deja_worktrees(repo: Path, corpus: Path) -> None:
    rutas: list[Path] = []

    def solve(worktree: Path, defect: object) -> None:
        rutas.append(worktree.resolve())

    FitnessScorer(repo, corpus, run_tests=_pytest_runner).score(solve=solve)

    assert rutas and all(not p.exists() for p in rutas)


def test_el_resultado_es_serializable(repo: Path, corpus: Path) -> None:
    score = FitnessScorer(repo, corpus, run_tests=_pytest_runner).score(
        solve=lambda w, x: None
    )

    d = json.loads(json.dumps(score.to_dict()))
    assert {"solved", "total", "ratio", "outcomes"} <= set(d)


def test_corpus_vacio_no_divide_por_cero(repo: Path, tmp_path: Path) -> None:
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("")

    score = FitnessScorer(repo, vacio, run_tests=_pytest_runner).score(
        solve=lambda w, x: None
    )

    assert score.total == 0
    assert score.ratio == 0.0


def test_score_por_defecto_no_intenta_nada(repo: Path, corpus: Path) -> None:
    """`solve=None` mide la línea base: cuánto se resuelve sin hacer nada."""
    score = FitnessScorer(repo, corpus, run_tests=_pytest_runner).score()

    assert score.solved == 0


def test_dataclass_default() -> None:
    assert FitnessScore().ratio == 0.0
