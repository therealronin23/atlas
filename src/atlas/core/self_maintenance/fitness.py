"""FitnessScorer — el número que el lazo de autoconstrucción tiene que subir.

Atlas tenía RESTRICCIONES ("pytest pasa", "mypy limpio", "no empeores el
recall") y ninguna FUNCIÓN DE FITNESS. Por eso rendía 7,8% end-to-end (13
aplicados de 167 en 71 días) frente al 35-50% de aceptación de PRs reales del
campo: sin una métrica que subir, un lazo sólo puede no-empeorar, y lo que sale
es un paseo aleatorio filtrado por tests.

DGM (arXiv:2505.22954, ICLR 2026) lo nombra: *probar que un cambio es netamente
beneficioso es imposible en la práctica*, así que hay que medirlo empíricamente
contra un banco. Ése es el ingrediente habilitante, y es el que faltaba.

La forma es deliberadamente la de `benchmark_gate.py` —dataclass con
`to_dict()`, runner inyectable, una entrada— porque ya existe y
`ColdUpdateBatcher` ya sabe consumirla. La DIFERENCIA es lo que mide, y lo es
todo: `BenchmarkGate` compara antes/después y responde "¿he empeorado?", que es
una restricción más. Esto responde "¿cuánto resuelvo?", que es lo único que
puede subir.

CÓMO NO SE HACKEA. El solver recibe un worktree con el código EN BASE y el test
del arreglo, nunca el diff de la solución: el corpus guarda `test_patch` y
jamás el parche de `src/`. La respuesta no vive en el repositorio, así que no
se puede leer — sólo resolver. Es la diferencia entre medir capacidad y medir
memoria, y es lo que falla en el 19,78% de "resueltos" de SWE-bench que en
realidad hackean el harness.

VALIDACIÓN DEL INSTRUMENTO. Un banco cuyo extremo perfecto no da 1.0 es
imposible de superar, y uno cuyo extremo nulo no da 0.0 mide otra cosa. Ambos
extremos están fijados con test — sobre un repositorio sintético, que es lo que
un test puede permitirse.

Eso NO basta para leer un resultado real, y hubo que aprenderlo: el 2026-08-10
los dos solvers sacaron 0/5 sobre defectos de verdad, y un cero no distingue
"los solvers no pueden" de "el banco es imposible". `OracleSolver` (en
`fitness_solvers`) aplica el arreglo real sobre el CORPUS REAL y `fitness_run`
lo ejecuta como control en cada pase: es la cota superior contra la que se lee
todo lo demás.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from atlas.core.self_maintenance.frozen_defects import FrozenDefect, TestRunner

__all__ = ["FitnessScore", "FitnessScorer", "Solver"]

#: Intento de resolución sobre un worktree preparado. Puede no hacer nada.
#: El `FrozenDefect` que recibe viene REDACTADO — ver `_redact`.
Solver = Callable[[Path, FrozenDefect], None]


def _redact(defect: FrozenDefect) -> FrozenDefect:
    """Quita del defecto todo lo que revelaría la solución.

    `subject` es el mensaje de commit del arreglo — "fix(watchdog): sabía ver
    «muerto», no sabía ver «vivo e inútil»" no es una pista, es la solución en
    prosa. `fix_sha` es peor: da acceso directo al diff con un `git show`. Y
    `test_patch` no hace falta, porque el test ya está materializado en el
    worktree; entregarlo sólo añade superficie por la que se filtre contexto
    del commit del arreglo.

    Un solver que lea eso mide comprensión lectora, no capacidad de ingeniería
    — el mismo vicio que hace falso el 19,78% de los "resueltos" de SWE-bench.

    Lo que SÍ conserva es lo que hace falta para trabajar: qué tests hay que
    poner en verde, y el id para poder correlacionar el resultado.
    """
    from dataclasses import replace

    return replace(defect, subject="", fix_sha="", test_patch="")


@dataclass(frozen=True)
class FitnessScore:
    """`solved/total`. `total` cuenta sólo defectos VERIFICADOS."""

    solved: int = 0
    total: int = 0
    outcomes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return (self.solved / self.total) if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "solved": self.solved,
            "total": self.total,
            "ratio": round(self.ratio, 4),
            "outcomes": list(self.outcomes),
        }


class FitnessScorer:
    """Puntúa un solver contra el corpus congelado."""

    def __init__(
        self,
        repo_root: Path,
        corpus_path: Path,
        *,
        run_tests: TestRunner,
    ) -> None:
        self._root = Path(repo_root)
        self._corpus = Path(corpus_path)
        self._run_tests = run_tests
        # Un nombre de worktree derivado sólo del id del defecto colisiona
        # entre pases simultáneos, y `git worktree add` falla sobre un path que
        # ya existe. `score()` captura ese fallo y lo anota como defecto NO
        # resuelto: un cero que no mide al solver sino al vecino. Es la misma
        # familia que el resto de esta auditoría —un error disfrazado de estado
        # normal— y aquí falsearía justo el número que el banco existe para dar.
        self._pass_id = uuid4().hex[:8]

    def defects(self) -> list[FrozenDefect]:
        """Sólo los VERIFICADOS. Un candidato sin verificar infla el
        denominador y haría parecer que el lazo empeora sin haber cambiado."""
        if not self._corpus.exists():
            return []
        out: list[FrozenDefect] = []
        for line in self._corpus.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                defect = FrozenDefect.from_dict(json.loads(line))
            except (ValueError, KeyError):
                continue
            if defect.verified:
                out.append(defect)
        return out

    def score(self, *, solve: Solver | None = None) -> FitnessScore:
        """Prepara cada defecto, deja que el solver lo intente, y mide.

        `solve=None` es la línea base honesta: cuánto se resuelve sin hacer
        nada. Debe dar 0 — si no, el banco no mide lo que dice medir.
        """
        from atlas.core.swarm_backend import WorktreeManager

        manager = WorktreeManager(self._root)
        solved = 0
        outcomes: list[dict[str, Any]] = []
        for defect in self.defects():
            outcome: dict[str, Any] = {"defect_id": defect.id, "solved": False}
            try:
                with manager.session(
                    f"fitness-score-{defect.id}-{self._pass_id}",
                    base_ref=defect.base_sha,
                ) as worktree:
                    # El montaje necesita `fix_sha`; el solver NO puede verlo.
                    # De ahí que la redacción vaya justo entre las dos cosas.
                    self._materialize_tests(worktree, defect)
                    if solve is not None:
                        solve(worktree, _redact(defect))
                    exit_code = self._run_tests(worktree, tuple(defect.test_files))
                    outcome["solved"] = exit_code == 0
            except Exception as exc:  # noqa: BLE001 — un defecto malo no cancela el pase
                outcome["reason"] = f"{type(exc).__name__}: {exc}"[:300]
            if outcome["solved"]:
                solved += 1
            outcomes.append(outcome)
        return FitnessScore(solved=solved, total=len(outcomes), outcomes=outcomes)

    def _materialize_tests(self, worktree: Path, defect: FrozenDefect) -> None:
        """Trae al worktree el test del arreglo, dejando el código en base.

        Con git, no aplicando el diff guardado: `checkout` sólo puede traer
        ficheros de un commit inmutable del mismo repositorio, así que es
        estrictamente más seguro que aplicar un parche arbitrario.
        """
        import subprocess

        from atlas.core.git_env import clean_git_env

        subprocess.run(
            ["git", "checkout", defect.fix_sha, "--", *defect.test_files],
            cwd=worktree,
            env=clean_git_env(),
            capture_output=True,
            check=True,
            timeout=60,
        )
