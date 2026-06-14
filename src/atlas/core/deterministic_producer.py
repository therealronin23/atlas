"""
Capa 3/ADR-048 fase C — DeterministicProducer: el arnés.

El productor más barato del lazo (`VerifiedProducer`). No llama a ningún modelo:
aplica transforms PUROS (texto/AST) sobre el fuente y emite un diff unificado
mínimo. Es el "arnés" en dos sentidos:

1. **Suelo barato**: para tareas mecánicas (whitespace, newline final, líneas en
   blanco al EOF) resuelve sin gastar un token. El LLM solo entra si esto no basta.
2. **Guardarraíl**: cada transform mantiene un INVARIANTE — si el fuente parseaba
   como Python, el resultado también debe parsear. Un transform que rompería el
   AST se descarta (no emite ese cambio). El arnés nunca produce un diff que
   destruya el árbol.

Determinista de punta a punta: misma entrada → mismo diff. Sin red, sin git, sin
subprocesos. El diff se calcula con `difflib`; quien lo aplica es otra capa.
"""

from __future__ import annotations

import ast
import difflib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from atlas.core.verify import Artifact, ArtifactKind, CostTier
from atlas.router.cascade import Difficulty, TaskSpec

if TYPE_CHECKING:
    from atlas.core.lesson_store import LessonStore


@dataclass(frozen=True)
class Transform:
    """Un transform puro `str -> str` con nombre estable (para señalizar tareas)."""

    name: str
    apply: Callable[[str], str]


def _strip_trailing_whitespace(source: str) -> str:
    return "\n".join(line.rstrip() for line in source.split("\n"))


def _ensure_final_newline(source: str) -> str:
    if source and not source.endswith("\n"):
        return source + "\n"
    return source


def _collapse_eof_blank_lines(source: str) -> str:
    # Reduce cualquier carrera de líneas en blanco al final a un único '\n'.
    stripped = source.rstrip("\n")
    if not stripped:
        return source
    return stripped + "\n"


# Orden estable: whitespace por línea → newline final → colapso EOF.
DEFAULT_TRANSFORMS: tuple[Transform, ...] = (
    Transform("strip_trailing_whitespace", _strip_trailing_whitespace),
    Transform("ensure_final_newline", _ensure_final_newline),
    Transform("collapse_eof_blank_lines", _collapse_eof_blank_lines),
)


def _parses(path: str, source: str) -> bool:
    """¿El fuente parsea como Python? Para no-Python el invariante no aplica."""
    if not path.endswith(".py"):
        return True
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def detect_transforms(
    path: str, source: str, transforms: Sequence[Transform] = DEFAULT_TRANSFORMS
) -> tuple[str, ...]:
    """Nombres de los transforms que CAMBIARÍAN este fuente (respetando el
    invariante AST). Lo usa el scout para señalizar tareas sin producir el diff."""
    names: list[str] = []
    base_ok = _parses(path, source)
    current = source
    for tf in transforms:
        candidate = tf.apply(current)
        if candidate == current:
            continue
        if base_ok and not _parses(path, candidate):
            continue  # rompería el AST: el arnés lo descarta
        names.append(tf.name)
        current = candidate
    return tuple(names)


class DeterministicProducer:
    """Conforma el Protocol `Producer` (capa 2). Lee `target_path` y `source`
    de `spec.metadata`, aplica los transforms y emite un `Artifact(PATCH)` con
    el diff unificado. Si nada cambia, emite un diff vacío (verdict de capa 1
    lo marcará: un diff sin hunks no pasa el UnifiedDiffVerifier)."""

    producer_id = "deterministic"
    # SHAPE, no STATIC: el productor corre `ast.parse` para sostener el invariante
    # (trabajo de análisis estático real), genuinamente más caro que el chequeo
    # de forma del diff (regex, STATIC) que lo verifica → la regla asimétrica
    # aplica honestamente (verificador más barato que productor).
    cost = CostTier.SHAPE
    capability = Difficulty.MECHANICAL

    def __init__(
        self,
        transforms: Sequence[Transform] = DEFAULT_TRANSFORMS,
        lesson_store: LessonStore | None = None,
    ) -> None:
        self._transforms = tuple(transforms)
        self._lesson_store = lesson_store

    def produce(self, spec: TaskSpec) -> Artifact:
        path = str(spec.metadata.get("target_path", ""))
        source = str(spec.metadata.get("source", ""))
        applied, result = self._apply(path, source)
        diff = self._unified_diff(path, source, result) if applied else ""
        return Artifact(
            kind=ArtifactKind.PATCH,
            payload={"diff": diff},
            producer_cost=self.cost,
            metadata={
                "allowed_paths": [path] if path else [],
                "transforms_applied": list(applied),
                "producer": self.producer_id,
            },
        )

    # ------------------------------------------------------------------

    def _apply(self, path: str, source: str) -> tuple[tuple[str, ...], str]:
        names: list[str] = []
        base_ok = _parses(path, source)
        current = source
        lessons = self._lesson_store.all() if self._lesson_store is not None else []
        avoid_patterns = [l.avoid_pattern for l in lessons if l.avoid_pattern]
        for tf in self._transforms:
            candidate = tf.apply(current)
            if candidate == current:
                continue
            if base_ok and not _parses(path, candidate):
                continue
            if any(p in candidate for p in avoid_patterns):
                continue
            names.append(tf.name)
            current = candidate
        return tuple(names), current

    @staticmethod
    def _unified_diff(path: str, before: str, after: str) -> str:
        if before == after:
            return ""
        label = path or "file"
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
            n=3,
        )
        return "".join(diff)
