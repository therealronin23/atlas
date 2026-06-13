"""
Capa 3/ADR-048 fase E — RepoMaintenanceScout: la fuente de tareas.

Escanea el repo y emite `MaintenanceTask` para cada fichero con un arreglo
mecánico detectable (los mismos transforms del arnés determinista). NO produce
diffs ni escribe nada: solo señala trabajo.

**Disciplina crítica — dedup contra propuestas abiertas.** El scout corre en
bucle; si re-propusiera tareas que ya tienen una propuesta ColdUpdate abierta,
acumularía duplicados — exactamente la clase de fuga que generó los 365 worktrees
huérfanos. Cada tarea lleva una `signature` estable (`{transform}:{path}`); el
scout recibe el conjunto de firmas YA abiertas y las omite. La ley de entrada del
scout: una tarea solo se emite si su firma no está abierta.

Puro: los ficheros se inyectan como `(path, source)` (los lee la capa de arriba,
que sí toca disco). Sin red, sin git.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from atlas.core.deterministic_producer import DEFAULT_TRANSFORMS, Transform, detect_transforms
from atlas.core.verify import ArtifactKind
from atlas.router.cascade import TaskSpec


@dataclass(frozen=True)
class MaintenanceTask:
    """Una unidad de mantenimiento señalada. `signature` es la clave de dedup."""

    path: str
    transform: str
    source: str = field(repr=False, default="")

    @property
    def signature(self) -> str:
        return f"{self.transform}:{self.path}"

    def to_spec(self) -> TaskSpec:
        """Convierte a `TaskSpec` consumible por el `VerifiedProducer`.
        `target_path` + `source` alimentan al DeterministicProducer;
        `allowed_paths` lo hace cumplir el UnifiedDiffVerifier."""
        return TaskSpec(
            # "formatea" hace que el estimador (capa 2) la clasifique MECHANICAL,
            # que es lo que es: el arnés determinista basta.
            intent=f"formatea {self.transform} en {self.path}",
            kind=ArtifactKind.PATCH,
            metadata={
                "target_path": self.path,
                "source": self.source,
                "allowed_paths": [self.path],
                "signature": self.signature,
                "risk": "low",
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "transform": self.transform, "signature": self.signature}


class RepoMaintenanceScout:
    """Detecta arreglos mecánicos y emite tareas dedup-adas contra lo abierto."""

    def __init__(self, transforms: Iterable[Transform] = DEFAULT_TRANSFORMS) -> None:
        self._transforms = tuple(transforms)

    def scan(
        self,
        files: Iterable[tuple[str, str]],
        *,
        open_signatures: frozenset[str] = frozenset(),
    ) -> list[MaintenanceTask]:
        """`files`: pares (path, source). `open_signatures`: firmas de tareas YA
        propuestas (dedup). Devuelve tareas nuevas, deterministas y sin duplicar
        — incluido contra otras tareas del mismo barrido."""
        tasks: list[MaintenanceTask] = []
        emitted: set[str] = set(open_signatures)
        for path, source in files:
            for name in detect_transforms(path, source, self._transforms):
                task = MaintenanceTask(path=path, transform=name, source=source)
                if task.signature in emitted:
                    continue
                emitted.add(task.signature)
                tasks.append(task)
        return tasks
