"""
Atlas Core — CodeCycle
Loop completo: Cónclave planifica → ParallelCoder construye → Cónclave audita → itera si falla.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from atlas.core.parallel_coder import ParallelCoder, ParallelCoderResult

__all__ = ["CodeCycle", "CycleResult"]

logger = logging.getLogger(__name__)

_PLANNING_PROMPT = """\
Eres un planificador de software. Descompón la siguiente tarea en subtareas independientes.
Responde ÚNICAMENTE con una lista numerada. Una subtarea por línea. Sin explicaciones.

Tarea: {task}

Contexto (archivos relevantes): {context_files}
"""

_NUMBERED_LINE_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")


@dataclass
class CycleResult:
    success: bool
    cycles: int                          # iteraciones del loop principal
    subtasks: list[str]                  # subtareas generadas en la planificación
    parallel_result: ParallelCoderResult | None
    council_verdict: str | None          # "pass" | "fail" | "unknown" | None
    error: str | None = None


class CodeCycle:
    """Loop completo de codificación con planificación y auditoría del Cónclave."""

    def __init__(
        self,
        hub: InferenceHub,
        *,
        repo_root: Path | None = None,
        timeout_s: int = 120,
        lesson_store: Any | None = None,
        # Si se inyecta, el veredicto del Cónclave (_council_review) se destila
        # en LessonStore vía LessonSynthesisRecorder (fix bug: antes de esto,
        # convene_for_decision se llamaba SIN synthesis_recorder aquí, y el
        # Cónclave deliberaba sin que nada de eso se aprendiera).
    ) -> None:
        self._hub = hub
        self._repo_root = repo_root or Path.cwd()
        self._timeout_s = timeout_s
        self._lesson_store = lesson_store

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        context_files: list[str],
        test_cmd: list[str],
        *,
        max_cycles: int = 2,
        level: InferenceLevel = InferenceLevel.L2,
    ) -> CycleResult:
        """
        Ejecuta el ciclo completo: planificar → construir en paralelo → auditar → reintentar.

        Parámetros
        ----------
        task:
            Descripción de la tarea de codificación.
        context_files:
            Rutas relativas al repo_root de los archivos de contexto.
        test_cmd:
            Comando para validar los cambios.
        max_cycles:
            Número máximo de iteraciones del loop principal.
        level:
            Nivel de inferencia para la planificación.
        """
        # Fase 1 — Planificación
        subtasks = self._plan(task, context_files, level)

        # Fase 2 — Loop
        parallel_result: ParallelCoderResult | None = None
        verdict_str: str | None = None
        remaining_subtasks = subtasks

        for cycle in range(1, max_cycles + 1):
            logger.debug("CodeCycle — ciclo %d/%d, subtareas: %d", cycle, max_cycles, len(remaining_subtasks))

            # Construir en paralelo
            pc = ParallelCoder(repo_root=self._repo_root, timeout_s=self._timeout_s)
            parallel_result = pc.run(remaining_subtasks, context_files, test_cmd, level=level)

            # Deliberación del Cónclave
            verdict_str = self._council_review(task, parallel_result)

            if verdict_str == "pass":
                return CycleResult(
                    success=True,
                    cycles=cycle,
                    subtasks=subtasks,
                    parallel_result=parallel_result,
                    council_verdict=verdict_str,
                )

            # Solo reintentar las subtareas que fallaron
            remaining_subtasks = [
                r.subtask for r in parallel_result.results if not r.coder_result.success
            ]
            if not remaining_subtasks:
                # Todos los workers pasaron pero Cónclave dijo fail → aceptar igualmente
                return CycleResult(
                    success=True,
                    cycles=cycle,
                    subtasks=subtasks,
                    parallel_result=parallel_result,
                    council_verdict=verdict_str,
                )

        return CycleResult(
            success=False,
            cycles=max_cycles,
            subtasks=subtasks,
            parallel_result=parallel_result,
            council_verdict=verdict_str,
        )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _plan(self, task: str, context_files: list[str], level: InferenceLevel) -> list[str]:
        """Llama al hub para descomponer la tarea en subtareas. Fallback: [task]."""
        prompt = _PLANNING_PROMPT.format(
            task=task,
            context_files=", ".join(context_files) if context_files else "(ninguno)",
        )
        request = InferenceRequest(
            prompt=prompt,
            level=level,
            task_id="code_cycle_plan",
            max_tokens=1024,
        )
        try:
            response = self._hub.infer(request)
            if not response.success or not response.text:
                logger.warning("CodeCycle: planificación falló (%s) — usando tarea completa", response.error)
                return [task]

            subtasks = [
                m.group(1).strip()
                for line in response.text.splitlines()
                if (m := _NUMBERED_LINE_RE.match(line))
            ]
            if not subtasks:
                logger.warning("CodeCycle: planificación no produjo subtareas — usando tarea completa")
                return [task]

            logger.debug("CodeCycle: %d subtareas generadas", len(subtasks))
            return subtasks

        except Exception as exc:  # noqa: BLE001
            logger.warning("CodeCycle: excepción en planificación (%s) — usando tarea completa", exc)
            return [task]

    def _council_review(self, task: str, result: ParallelCoderResult) -> str:
        """Convoca el Cónclave para revisar los resultados del build. Devuelve 'pass'|'fail'|'unknown'."""
        try:
            from atlas.core.deliberation_council import (
                LessonSynthesisRecorder, convene_for_decision,
            )
            from atlas.router.cascade import Difficulty

            passed = sum(1 for r in result.results if r.coder_result.success)
            total = result.subtasks_total
            summary = f"{passed}/{total} subtareas pasaron tests. Tarea original: {task}"
            failed_details = "; ".join(
                f"{r.subtask[:60]}: {r.coder_result.error or 'tests fallaron'}"
                for r in result.results if not r.coder_result.success
            )
            if failed_details:
                summary += f"\nFallos: {failed_details}"

            recorder = (
                LessonSynthesisRecorder(self._lesson_store)
                if self._lesson_store is not None else None
            )
            evidence = convene_for_decision(
                decision=summary,
                context=task[:1000],
                difficulty=Difficulty.HARD,
                risk="modificación de código de producción",
                irreversible=False,
                synthesis_recorder=recorder,
            )
            if evidence is None:
                # Cónclave no convocado (trivial) → aceptar si todos pasaron
                return "pass" if result.success else "fail"
            return evidence.verdict.value

        except Exception as exc:  # noqa: BLE001
            logger.warning("Cónclave no disponible: %s — usando resultado de tests", exc)
            return "pass" if result.success else "fail"
