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
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.core.self_maintenance.frozen_defects import FrozenDefect

__all__ = ["AtlasSolver", "DirectModelSolver", "OracleSolver", "SolverAttempt"]

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

#: El MISMO intérprete que puntúa, no el que salga en PATH.
#:
#: `AtlasSolver` le pasaba a ToolCoder `test_cmd=["python", ...]`. Comprobado el
#: 2026-08-10: el banco se lanza con `.venv/bin/python` pero `.venv/bin` NO está
#: en PATH, así que ese `python` era `/usr/bin/python` — otro intérprete, con
#: otro pytest (9.1.0) y otras versiones de dependencias. ToolCoder iteraba
#: contra un entorno y `FitnessScorer` puntuaba contra otro: la señal que guía
#: al modelo y la que decide el resultado podían discrepar sin que nada lo
#: dijera. Si mañana el sistema no trae pytest, además, el fallo sería
#: `test_cmd no encontrado` en los 19 defectos y el número saldría 0 sin que
#: nadie hubiera medido nada.
_PYTHON = sys.executable or "python"


def _strip_thinking(text: str) -> str:
    """Quita bloques `<think>` cerrados; conserva uno sin cerrar.

    Un bloque abierto significa que el modelo se quedó sin presupuesto: mejor
    devolver el texto ruidoso que vaciarlo y perder la única señal que llegó.
    Mismo criterio que `deliberation_council._strip_thinking`.
    """
    return _THINK_BLOCK.sub("", text).strip()

@dataclass(frozen=True)
class SolverAttempt:
    """Qué hizo el solver, al margen de si el defecto quedó resuelto.

    Medido el 2026-08-10: `atlas_toolcoder` sacó 0/5 en tres tiradas y el banco
    no sabía decir por qué. `coder.code()` devuelve un `CoderResult` con el
    error, las iteraciones y los ficheros tocados, y el solver lo descartaba.
    Un cero sin causa no distingue "el modelo no supo" de "el proveedor no
    contestó" ni de "el comando de test no existía" — tres diagnósticos con
    tres arreglos distintos, y la información estaba delante.

    `ok` significa "el solver hizo su trabajo", NO "resolvió el defecto": quien
    decide lo segundo es pytest, en `FitnessScorer`.
    """

    defect_id: str
    ok: bool
    detail: str = ""
    files_changed: tuple[str, ...] = ()
    iterations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "defect_id": self.defect_id, "ok": self.ok, "detail": self.detail,
            "files_changed": list(self.files_changed), "iterations": self.iterations,
        }


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
        self.attempts: list[SolverAttempt] = []

    def __call__(self, worktree: Path, defect: FrozenDefect) -> None:
        try:
            coder = (self._factory or self._default_coder)(worktree)
            resultado = coder.code(
                task=_INSTRUCCION.format(targets=", ".join(defect.test_files)),
                context_files=list(defect.test_files),
                test_cmd=[_PYTHON, "-m", "pytest", *defect.test_files, "-q"],
                max_iterations=self._max_iterations,
            )
        except Exception as exc:  # noqa: BLE001 — un defecto malo no cancela el pase
            logger.warning("AtlasSolver falló en %s: %s", defect.id, exc)
            self.attempts.append(
                SolverAttempt(defect.id, False, f"{type(exc).__name__}: {exc}"[:300])
            )
            return
        ok = bool(getattr(resultado, "success", False))
        self.attempts.append(
            SolverAttempt(
                defect_id=defect.id,
                ok=ok,
                detail=str(getattr(resultado, "error", "") or "")[:300],
                files_changed=tuple(getattr(resultado, "files_changed", ()) or ()),
                iterations=int(getattr(resultado, "iterations", 0) or 0),
            )
        )
        if not ok:
            logger.info(
                "AtlasSolver no cerró %s en %s iteraciones: %s",
                defect.id, self.attempts[-1].iterations, self.attempts[-1].detail,
            )

    @staticmethod
    def _default_coder(worktree: Path) -> Any:
        from atlas.core.inference_hub import InferenceHub
        from atlas.core.tool_coder import ToolCoder

        # repo_root = el WORKTREE, nunca el checkout vivo del operador.
        return ToolCoder(InferenceHub(mode="auto"), repo_root=worktree)


class OracleSolver:
    """El **control** del instrumento: aplica el arreglo real. Cota superior.

    No compite. Hace trampa a propósito, y por eso su número no va en la tabla
    de comparación — enfrentar un solver honesto a uno que ve la solución sólo
    produciría un "aporte del harness" negativo y sin sentido.

    Existe por una razón concreta y medida. El 2026-08-10, sobre 5 defectos
    reales y 3 tiradas, `baseline` y `atlas_toolcoder` sacaron ambos 0/5. Un
    cero admite dos lecturas incompatibles:

        (a) los solvers no son capaces todavía  -> el número es real
        (b) el banco es imposible de superar    -> el número no mide nada

    Sin el oráculo no hay forma de elegir, y publicar un 0 sin saber cuál de las
    dos es sería peor que no medir. Los extremos del scorer estaban validados,
    pero sobre un repositorio de juguete de un defecto sintético: el docstring
    prometía "el arreglo real -> 19/19" y esa ejecución nunca había ocurrido.

    Trae del commit del arreglo todo lo que NO esté bajo `tests/`: el montaje ya
    puso el examen, y volver a traerlo abriría la puerta a que un arreglo que
    relajó su propio test se contase como resuelto.
    """

    def __init__(self, repo_root: Path, defects: Sequence[FrozenDefect]) -> None:
        self._root = Path(repo_root)
        self._fix_sha = {d.id: d.fix_sha for d in defects if d.fix_sha}
        if not self._fix_sha:
            # Un oráculo vacío puntuaría 0/N y se leería como "el banco es
            # imposible": exactamente el diagnóstico invertido que evita.
            raise ValueError(
                "OracleSolver necesita el corpus SIN redactar; "
                f"recibió {len(defects)} defectos sin fix_sha"
            )

    def __call__(self, worktree: Path, defect: FrozenDefect) -> None:
        fix = self._fix_sha.get(defect.id)
        if not fix:
            raise KeyError(f"el oráculo no conoce el defecto {defect.id}")
        rutas = self._non_test_paths(fix)
        if not rutas:
            raise RuntimeError(f"el arreglo {fix[:12]} no toca código fuera de tests/")
        self._git(["checkout", fix, "--", *rutas], cwd=worktree)

    def _non_test_paths(self, fix: str) -> list[str]:
        """Ficheros del commit que no son tests, sin los borrados.

        `git show` en vez de `<sha>^..<sha>` para que un commit raíz no rompa.
        Un borrado no se puede `checkout` y haría fallar la orden entera.
        """
        salida = self._git(["show", "--name-status", "--format=", "-m", fix])
        rutas: list[str] = []
        for linea in salida.splitlines():
            campos = linea.split("\t")
            if len(campos) < 2 or campos[0].startswith("D"):
                continue
            # Un rename llega como `R100 <viejo> <nuevo>`: interesa el destino.
            ruta = campos[-1].strip()
            if ruta and not ruta.startswith("tests/"):
                rutas.append(ruta)
        return sorted(set(rutas))

    def _git(self, args: list[str], *, cwd: Path | None = None) -> str:
        from atlas.core.git_env import clean_git_env

        return subprocess.run(
            ["git", *args],
            cwd=cwd or self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout


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
        self.attempts: list[SolverAttempt] = []

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
                error = str(getattr(response, "error", "") or "")
                logger.warning(
                    "DirectModelSolver sin respuesta en %s: %s", defect.id, error,
                )
                # "No contestó" no es "no supo". Medido el 2026-08-10: 3 de 5
                # defectos agotaron los 300 s, y contarlos como fallos de
                # capacidad confundiría infraestructura con inteligencia.
                self.attempts.append(SolverAttempt(defect.id, False, error[:300]))
                return
            escritos = self._apply(
                worktree, _strip_thinking(str(getattr(response, "text", "") or ""))
            )
            self.attempts.append(
                SolverAttempt(
                    defect_id=defect.id,
                    ok=bool(escritos),
                    detail="" if escritos else "respuesta sin bloques de código",
                    files_changed=tuple(escritos),
                    iterations=1,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("DirectModelSolver falló en %s: %s", defect.id, exc)
            self.attempts.append(
                SolverAttempt(defect.id, False, f"{type(exc).__name__}: {exc}"[:300])
            )

    @staticmethod
    def _default_hub() -> Any:
        from atlas.core.inference_hub import InferenceHub

        return InferenceHub(mode="auto")

    @staticmethod
    def _apply(worktree: Path, text: str) -> list[str]:
        """Escribe los bloques devueltos y devuelve qué escribió, con dos cerrojos.

        1. Nada fuera del worktree: un `../` en la ruta que devuelve el modelo
           no puede salir del jaulón.
        2. Nada bajo `tests/`: resolver el defecto reescribiendo el examen es
           la forma más barata de hackear el banco.
        """
        escritos: list[str] = []
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
                escritos.append(str(destino.relative_to(root)))
            except OSError as exc:
                logger.warning("no se pudo escribir %s: %s", rel, exc)
        return escritos
