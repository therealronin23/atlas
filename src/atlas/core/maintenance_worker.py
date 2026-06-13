"""
Capa 3/ADR-048 fase F — Integración: del scout al worker, vía VerifiedProducer.

Cablea las piezas A–E en un `produce_diff` para `WorktreeWorker`:

    scout → MaintenanceTask → VerifiedProducer(det[+llm], verify, panel?) → diff
          → worker (valida en worktree) → blackboard → reconciler → ColdUpdate

`build_maintenance_producer` compone el lazo con el arnés determinista (siempre)
y, opcionalmente, el potenciador LLM. El verificador de capa 1 por defecto es el
`UnifiedDiffVerifier` (STATIC, más barato que ambos productores → cumple la regla
asimétrica). El panel y el grounding son opcionales (gating los salta para lo
mecánico, que es el grueso del mantenimiento).

`maintenance_produce_diff` adapta el `VerifiedProducer` (que habla TaskSpec→
ProduceOutcome) a la firma que `WorktreeWorker` espera (`(task, path) -> str`).
Devuelve el diff SOLO si el lazo lo verificó; si no, cadena vacía (el worker y el
coordinador lo tratan como fallo honesto, no como un PASS fingido).

**Auto-apply sigue APAGADO**: esto produce y verifica; aplicar es del reconciler
→ decider, fuera de este módulo. Nada aquí escribe Merkle ni toca el ATLAS_HOME
vivo (el worker es productor puro, ADR-046).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas.core.deterministic_producer import DeterministicProducer
from atlas.core.llm_producer import LLMProducer
from atlas.core.maintenance_scout import MaintenanceTask
from atlas.core.verified_producer import GroundingSource, LearningSink, VerifiedProducer
from atlas.core.verify import UnifiedDiffVerifier, UniversalVerifier
from atlas.router.cascade import Producer


def build_maintenance_producer(
    *,
    llm: Producer | None = None,
    verifier: UniversalVerifier | None = None,
    panel: Any | None = None,
    grounding: GroundingSource | None = None,
    learning: LearningSink | None = None,
    budget_units: int = 1000,
) -> VerifiedProducer:
    """Lazo de mantenimiento: arnés determinista (siempre) + LLM opcional."""
    producers: list[Producer] = [DeterministicProducer()]
    if llm is not None:
        producers.append(llm if isinstance(llm, LLMProducer) else LLMProducer(llm))
    return VerifiedProducer(
        producers,
        verifier or UniversalVerifier([UnifiedDiffVerifier()]),
        panel=panel,
        grounding=grounding,
        learning=learning,
        budget_units=budget_units,
    )


def maintenance_produce_diff(
    producer: VerifiedProducer,
) -> Callable[[MaintenanceTask, Path], str]:
    """Adapta el VerifiedProducer a la firma `produce_diff` del WorktreeWorker.
    El `path` del worktree se ignora aquí: la tarea ya trae el `source` (el scout
    lo capturó); el diff es contra ese contenido, no contra el disco vivo."""

    def _produce_diff(task: MaintenanceTask, path: Path) -> str:
        outcome = producer.produce(task.to_spec())
        if not outcome.verified or outcome.artifact is None:
            return ""
        return str(outcome.artifact.payload.get("diff", ""))

    return _produce_diff
