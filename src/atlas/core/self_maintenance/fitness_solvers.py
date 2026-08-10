"""Los dos solvers del banco congelado, y por qué son dos.

`AtlasSolver` usa el motor real de Atlas —`ToolCoder`, con su ciclo
infer → edit → test, sus lecciones, su contexto institucional y sus
reintentos—. `DirectModelSolver` da el mismo problema a un modelo desnudo por
`InferenceHub`, sin ninguna de esas capas.

**La diferencia entre los dos es el resultado que importa.** No "¿cuánto
resuelve Atlas?" sino "¿cuánto aporta el harness?". Es una pregunta abierta con
un indicio incómodo: el lazo lleva 7,8% de aceptación end-to-end frente al
35-50% del campo, y nadie ha comprobado nunca si las capas suman o restan.
Un banco con un solo solver no puede responderla.

Ninguno de los dos ve la solución: el `FrozenDefect` llega redactado
(`fitness._redact` quita `subject`, `fix_sha` y `test_patch`) y estos solvers
tampoco los reconstruyen. `DirectModelSolver` además tiene prohibido escribir
en `tests/` — resolver el defecto cambiando el examen sería la forma más barata
de hackear el banco, y es exactamente lo que hace falso el 19,78% de los
"resueltos" de SWE-bench.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas.core.self_maintenance.frozen_defects import FrozenDefect

__all__ = ["AtlasSolver", "DirectModelSolver"]

logger = logging.getLogger(__name__)

#: ```python:ruta/al/fichero.py
#: <contenido>
#: ```
_BLOQUE = re.compile(
    r"```(?:[a-zA-Z]*):(?P<path>[^\n`]+)\n(?P<body>.*?)```", re.DOTALL
)

#: Mismo problema, misma solución que en `deliberation_council` y `atlas_coder`:
#: los modelos de razonamiento gastan el presupuesto en `<think>` y lo que
#: llega truncado es la SUSTANCIA, no el preámbulo.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

#: 2048 ahogaba a los modelos de razonamiento. Medido en la primera tirada real
#: (2026-08-09): `groq_qwen3` devolvió 6.929 caracteres, TODOS dentro de un
#: `<think>` sin cerrar, y cero bloques de código — el presupuesto se agotó a
#: mitad del razonamiento. El resultado fue `modelo_desnudo 0/3`, que no medía
#: al modelo sino a este fichero. Es exactamente el bug que el Cónclave ya
#: había pagado y documentado (`_REVIEW_MAX_TOKENS = 4096`), reintroducido aquí
#: por no mirar el prior art. Se sube y se deja env para poder subirlo más.
DEFAULT_MAX_TOKENS = 4096

#: El tope duro global de `InferenceHub` son 120 s, pensado para que un
#: proveedor colgado no bloquee al caller interactivo (Cónclave >20 min,
#: 2026-07-17). Es correcto ahí y demasiado corto AQUÍ: medido el 2026-08-09,
#: con 4096 tokens los modelos de razonamiento chocaban con él
#: (`TimeoutError: hard timeout tras 120.0s`) y el banco quedaba sesgado a
#: favor de Atlas — el solver desnudo competía con una mano atada.
#:
#: Se sube SÓLO para el banco, por petición: `InferenceRequest.timeout_s` ya
#: existía como campo y nadie lo usaba. Desde 2026-07-30 es un presupuesto
#: TOTAL de pared, no un tope por intento, así que subirlo no se multiplica por
#: la cadena de fallback. El daemon interactivo no cambia.
DEFAULT_TIMEOUT_S = 300.0


def _strip_thinking(text: str) -> str:
    """Quita bloques `<think>` cerrados; conserva uno sin cerrar.

    Un bloque abierto significa que el modelo se quedó sin presupuesto: mejor
    devolver el texto ruidoso que vaciarlo y perder la única señal que llegó.
    Mismo criterio que `deliberation_council._strip_thinking`.
    """
    return _THINK_BLOCK.sub("", text).strip()

_INSTRUCCION = (
    "Un test de este repositorio falla. Haz que pase modificando SÓLO el código "
    "fuente. No toques ficheros bajo tests/: el test define el comportamiento "
    "correcto y cambiarlo no resuelve nada.\n\n"
    "Tests que deben pasar: {targets}\n"
)


def _prompt(worktree: Path, defect: FrozenDefect) -> str:
    partes = [_INSTRUCCION.format(targets=", ".join(defect.test_files))]
    for rel in defect.test_files:
        path = worktree / rel
        try:
            partes.append(f"\n--- {rel} ---\n{path.read_text(encoding='utf-8')[:4000]}")
        except OSError:
            continue
    partes.append(
        "\nResponde con uno o más bloques con esta forma exacta, y nada más:\n"
        "```python:ruta/relativa/al/fichero.py\n<contenido COMPLETO del fichero>\n```\n"
    )
    return "\n".join(partes)


class AtlasSolver:
    """El motor real de Atlas contra el banco."""

    def __init__(
        self,
        *,
        coder_factory: Callable[[Path], Any] | None = None,
        max_iterations: int = 3,
    ) -> None:
        self._factory = coder_factory
        self._max_iterations = max_iterations

    def __call__(self, worktree: Path, defect: FrozenDefect) -> None:
        try:
            coder = (self._factory or self._default_coder)(worktree)
            coder.code(
                task=_INSTRUCCION.format(targets=", ".join(defect.test_files)),
                context_files=list(defect.test_files),
                test_cmd=["python", "-m", "pytest", *defect.test_files, "-q"],
                max_iterations=self._max_iterations,
            )
        except Exception as exc:  # noqa: BLE001 — un defecto malo no cancela el pase
            logger.warning("AtlasSolver falló en %s: %s", defect.id, exc)

    @staticmethod
    def _default_coder(worktree: Path) -> Any:
        from atlas.core.inference_hub import InferenceHub
        from atlas.core.tool_coder import ToolCoder

        # repo_root = el WORKTREE, nunca el checkout vivo del operador.
        return ToolCoder(InferenceHub(mode="auto"), repo_root=worktree)


class DirectModelSolver:
    """Un modelo desnudo contra el mismo banco, sin las capas de Atlas."""

    def __init__(
        self,
        *,
        hub: Any | None = None,
        max_tokens: int | None = None,
        level: Any | None = None,
        timeout_s: float | None = None,
    ) -> None:
        import os

        self._hub = hub
        if max_tokens is None:
            raw = os.environ.get("ATLAS_FITNESS_MAX_TOKENS", "").strip()
            max_tokens = int(raw) if raw.isdigit() else DEFAULT_MAX_TOKENS
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s if timeout_s is not None else DEFAULT_TIMEOUT_S
        self._level = level

    def __call__(self, worktree: Path, defect: FrozenDefect) -> None:
        try:
            from atlas.core.inference_hub import InferenceLevel, InferenceRequest

            hub = self._hub if self._hub is not None else self._default_hub()
            response = hub.infer(
                InferenceRequest(
                    prompt=_prompt(worktree, defect),
                    level=self._level or InferenceLevel.L1,
                    max_tokens=self._max_tokens,
                    temperature=0.1,
                    timeout_s=self._timeout_s,
                )
            )
            if not getattr(response, "success", False):
                logger.warning(
                    "DirectModelSolver sin respuesta en %s: %s",
                    defect.id, getattr(response, "error", ""),
                )
                return
            self._apply(worktree, _strip_thinking(str(getattr(response, "text", "") or "")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("DirectModelSolver falló en %s: %s", defect.id, exc)

    @staticmethod
    def _default_hub() -> Any:
        from atlas.core.inference_hub import InferenceHub

        return InferenceHub(mode="auto")

    @staticmethod
    def _apply(worktree: Path, text: str) -> None:
        """Escribe los bloques devueltos, con dos cerrojos.

        1. Nada fuera del worktree: un `../` en la ruta que devuelve el modelo
           no puede salir del jaulón.
        2. Nada bajo `tests/`: resolver el defecto reescribiendo el examen es
           la forma más barata de hackear el banco.
        """
        root = worktree.resolve()
        for match in _BLOQUE.finditer(text):
            rel = match.group("path").strip()
            if not rel or rel.startswith("/"):
                continue
            destino = (root / rel).resolve()
            if not destino.is_relative_to(root):
                logger.warning("bloque fuera del worktree, descartado: %s", rel)
                continue
            if destino.relative_to(root).parts[:1] == ("tests",):
                logger.warning("bloque sobre tests/, descartado: %s", rel)
                continue
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(match.group("body"), encoding="utf-8")
            except OSError as exc:
                logger.warning("no se pudo escribir %s: %s", rel, exc)
