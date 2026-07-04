"""Wrapper genérico sobre openevolve (codelion/openevolve, PyPI, 6.6k stars):
selección evolutiva REAL — islas + mutación + evaluador — a la escala de UNA
pieza de código, no de un agente completo.

Cierra la sustitución del "aprendizaje evolutivo por categorías" que el
Cónclave tumbó con razón: sin variantes reales compitiendo, aquello era solo
estadística sobre categorías sin mecanismo causal, no evolución de verdad.
Aquí sí hay variantes reales generadas y puntuadas por un evaluador real.

TODO(evolution+self-build): el cableado a SelfBuildRunner con un evaluador
que aplique cada variante a un worktree real y corra los tests reales del
backlog item es la SIGUIENTE tarea — fuera de alcance de este slice, no
fingido aquí. Este slice es SOLO el wrapper genérico: código inicial +
función evaluadora → mejor variante.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Union


@dataclass
class EvolutionOutcome:
    """Resultado de una corrida de evolución. ``succeeded=False`` cuando
    openevolve falló por cualquier motivo (ver ``EvolutionGate.evolve``) —
    nunca es un error que se propaga, solo falta de señal."""

    succeeded: bool
    best_code: str = ""
    best_score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "best_code": self.best_code,
            "best_score": self.best_score,
            "reason": self.reason,
        }


class EvolutionGate:
    """Envuelve openevolve (codelion/openevolve, selección evolutiva REAL:
    islas + mutación + evaluador) para generar y puntuar variantes de código
    a la escala de UNA pieza — no un linaje completo de agente (corrección
    del Cónclave: "categorías de cambio" sin variantes reales competiendo
    era estadística sin mecanismo causal, no evolución de verdad).

    TODO(evolution+self-build): el cableado a SelfBuildRunner con un
    evaluador que aplique cada variante a un worktree real y corra los
    tests reales del backlog item es la SIGUIENTE tarea — fuera de
    alcance aquí, no fingido. Este slice es el wrapper genérico:
    código inicial + evaluador → mejor variante."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        iterations: int = 10,
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._model = model
        self._iterations = iterations

    def evolve(
        self,
        *,
        initial_code: str,
        evaluator: Union[Callable[[str], dict[str, Any]], str, Path],
    ) -> EvolutionOutcome:
        """Evoluciona ``initial_code`` usando el ``evaluator`` dado — un
        callable (recibe la ruta de un fichero con el candidato, devuelve un
        dict de métricas) O una ruta a un fichero .py autocontenido con una
        función ``evaluate(program_path)`` a nivel de módulo (necesario
        cuando el llamador no puede darnos un callable sin closures, ver
        ``self_build_runner._write_worktree_evaluator_file`` — openevolve
        extrae el CÓDIGO FUENTE de los callables vía ``inspect.getsource`` y
        lo re-ejecuta aislado, así que un closure no sobrevive el viaje).
        Misma interfaz que espera ``openevolve.run_evolution``. Fail-open:
        CUALQUIER excepción (config inválida, API caída, timeout, etc.)
        devuelve ``EvolutionOutcome(succeeded=False, reason=...)`` — nunca
        propaga, esto es una optimización opcional, nunca debe tumbar el
        pipeline que lo invoca."""
        try:
            from openevolve.api import run_evolution
            from openevolve.config import Config, LLMConfig, LLMModelConfig

            config = Config(max_iterations=self._iterations)
            config.llm = LLMConfig(
                api_base=self._api_base,
                api_key=self._api_key,
                models=[LLMModelConfig(name=self._model, weight=1.0)],
            )
            result = run_evolution(
                initial_program=initial_code,
                evaluator=evaluator,
                config=config,
                iterations=self._iterations,
            )
        except Exception as exc:  # noqa: BLE001 — señal opcional, nunca bloquea
            return EvolutionOutcome(succeeded=False, reason=f"evolución falló: {exc}")

        return EvolutionOutcome(
            succeeded=True,
            best_code=result.best_code,
            best_score=float(result.best_score),
        )
