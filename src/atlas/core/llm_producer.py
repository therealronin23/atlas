"""
Capa 3/ADR-048 fase D — LLMProducer: el potenciador.

Envuelve un productor LLM interno (típicamente `InferenceProducer` de la capa 2)
y le añade dos cosas que el arnés determinista da gratis pero el modelo no:

1. **Restricciones de lección** (capa 4): los `avoid_pattern` de las lecciones
   cargadas se inyectan como prohibiciones explícitas en el contexto ("NO hagas
   X — ya falló antes"). Así el LLM *evoluciona*: cada lección aprendida acota su
   espacio de salida en el siguiente intento. El grounding del lazo aporta el
   texto; este productor lo eleva a restricción dura del prompt.
2. **`allowed_paths`** en el artefacto: el modelo no decide qué ficheros puede
   tocar; lo hereda de la tarea y el `UnifiedDiffVerifier` (capa 1) lo hace
   cumplir. El potenciador propone dentro de los límites del arnés.

Composición pura: el productor interno se inyecta (Protocol `Producer`). En tests,
un fake — sin red.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from atlas.core.verify import Artifact, ArtifactKind, CostTier
from atlas.router.cascade import Difficulty, Producer, TaskSpec

if TYPE_CHECKING:
    from atlas.core.lesson_store import LessonStore


class LLMProducer:
    """Decora un `Producer` LLM con restricciones de lección y allowed_paths."""

    def __init__(
        self,
        inner: Producer,
        *,
        avoid_patterns: Sequence[str] = (),
        lesson_store: "LessonStore | None" = None,
    ) -> None:
        self._inner = inner
        self._avoid = tuple(avoid_patterns)
        self._lesson_store = lesson_store

    @property
    def producer_id(self) -> str:
        return f"llm:{self._inner.producer_id}"

    @property
    def cost(self) -> CostTier:
        return self._inner.cost

    @property
    def capability(self) -> Difficulty:
        return self._inner.capability

    def produce(self, spec: TaskSpec) -> Artifact:
        constrained = self._with_constraints(spec)
        artifact = self._inner.produce(constrained)
        # Estampa allowed_paths desde la tarea: el modelo no los elige.
        allowed = spec.metadata.get("allowed_paths")
        if allowed is not None and "allowed_paths" not in artifact.metadata:
            artifact = replace(
                artifact, metadata={**artifact.metadata, "allowed_paths": list(allowed)}
            )
        if self._lesson_store is not None:
            diff = artifact.payload.get("diff", "")
            for lesson in self._lesson_store.all():
                heuristic = lesson.detection_heuristic
                if heuristic and heuristic in diff:
                    return replace(artifact, payload={"diff": ""})
        return artifact

    def _with_constraints(self, spec: TaskSpec) -> TaskSpec:
        if not self._avoid:
            return spec
        prohibitions = "\n".join(f"- NO {p}" for p in self._avoid)
        block = "Restricciones aprendidas (violarlas ya causó un fallo):\n" + prohibitions
        existing = str(spec.metadata.get("context", ""))
        context = f"{existing}\n\n{block}".strip() if existing else block
        return replace(spec, metadata={**spec.metadata, "context": context})
