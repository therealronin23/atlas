"""
Atlas Core — IncrementalCoder

Rebasa el límite medido de AtlasCoder (experimento sandbox 2026-06-27: falla
en features multi-pieza nuevas aunque el Cónclave delibere el plan): en vez de
pedir N piezas en una llamada, ejecuta una secuencia de incrementos de UNA
pieza cada uno, verificando cada incremento antes de pasar al siguiente.

Es el patrón que SÍ funcionó toda la sesión (cada técnica del harness survey
se implementó como cambios de 1-3 líneas verificados uno a uno) elevado a
estructura: el planificador (humano o Claude) escribe los incrementos con su
verificación; AtlasCoder ejecuta cada uno con sandbox; el que falla corta la
secuencia sin dañar nada (los anteriores ya verificados se quedan).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from atlas.core.atlas_coder import AtlasCoder, CoderResult

__all__ = ["Increment", "IncrementalResult", "IncrementalCoder"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Increment:
    """Un paso atómico de una feature multi-pieza.

    *task* debe describir UNA sola pieza (un parámetro, un método, un wiring).
    *test_cmd* debe verificar ESPECÍFICAMENTE esa pieza (lección del
    experimento: tests que no ejercitan la pieza dan falsos positivos).
    """

    task: str
    context_files: list[str]
    test_cmd: list[str]
    max_iterations: int = 3


@dataclass
class IncrementalResult:
    success: bool
    completed: int            # incrementos que pasaron
    total: int
    results: list[CoderResult] = field(default_factory=list)
    failed_increment: int | None = None  # índice 0-based del que falló


class IncrementalCoder:
    """Ejecuta una secuencia de incrementos de una pieza, cortando al primero
    que falla (los anteriores, ya verificados, se conservan).

    Cada incremento corre con sandbox=True por defecto: si falla, el repo real
    no se toca para ese incremento — la secuencia queda en el último estado
    verificado, nunca a medias dentro de una pieza.
    """

    def __init__(self, coder: AtlasCoder, *, sandbox: bool = True) -> None:
        self._coder = coder
        self._sandbox = sandbox

    def run(self, increments: list[Increment], **coder_kwargs: object) -> IncrementalResult:
        """Ejecuta los incrementos en orden. *coder_kwargs* se pasa a cada
        AtlasCoder.code() (ej. edit_format, use_apply_model, repo_map_files)."""
        results: list[CoderResult] = []
        for idx, inc in enumerate(increments):
            logger.info(
                "IncrementalCoder: incremento %d/%d — %s",
                idx + 1, len(increments), inc.task[:80],
            )
            result = self._coder.code(
                task=inc.task,
                context_files=inc.context_files,
                test_cmd=inc.test_cmd,
                max_iterations=inc.max_iterations,
                sandbox=self._sandbox,
                **coder_kwargs,  # type: ignore[arg-type]
            )
            results.append(result)
            # Lección del lote A-D (2026-06-28): un "éxito" con files_changed
            # vacío es el falso positivo medido en vivo (el test del incremento
            # no ejercitaba su pieza). Se trata como fallo de la secuencia —
            # no se avanza sobre una pieza que nunca se implementó.
            if result.success and getattr(result, "suspicious_no_op", False):
                logger.warning(
                    "IncrementalCoder: incremento %d reportó success=True SIN "
                    "cambios reales (files_changed=[]) — tratado como fallo, "
                    "posible falso positivo. Revisa si test_cmd ejercita la "
                    "pieza de este incremento.",
                    idx + 1,
                )
                return IncrementalResult(
                    success=False,
                    completed=idx,
                    total=len(increments),
                    results=results,
                    failed_increment=idx,
                )
            if not result.success:
                logger.warning(
                    "IncrementalCoder: incremento %d falló (%s) — secuencia "
                    "cortada; %d incrementos anteriores conservados.",
                    idx + 1, result.error, idx,
                )
                return IncrementalResult(
                    success=False,
                    completed=idx,
                    total=len(increments),
                    results=results,
                    failed_increment=idx,
                )
        return IncrementalResult(
            success=True,
            completed=len(increments),
            total=len(increments),
            results=results,
        )
