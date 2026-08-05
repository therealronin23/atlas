"""Pre-chequeo barato antes de la validación cara.

Extracción de la TÉCNICA del LSP de Hermes, no del paquete. Sus 4.704 loc de
`agent/lsp/` usan un único grupo de métodos del protocolo
(``textDocument/diagnostic``, ``publishDiagnostics``, ``didOpen/didChange/
didSave``): es una tubería de diagnósticos, no navegación de símbolos. Su valor
real cabe en una frase — **enterarse del error sin ejecutar todo**.

Coste medido en esta máquina (2026-08-05):

===========================  ==============
``ast.parse`` de un fichero  ~0 ms
``mypy`` de un fichero       249 ms
``pytest`` de un fichero     3.195 ms
suite completa               562.000 ms
===========================  ==============

`ToolCoder` y el lazo de evolución iban directos al ``test_cmd``. Un candidato
generado que ni siquiera parsea —el modo de fallo más común de un LLM que
escribe código— se llevaba por delante hasta 562 s de suite para acabar
puntuando 0.0 igualmente.

**Severidad, deliberada y asimétrica**: un fichero que no PARSEA no puede estar
bien nunca, así que es rechazo duro. Un error de TIPO se reporta pero no
rechaza — mypy da falsos positivos cuando faltan stubs o el entorno no es el
del proyecto (y aquí corre dentro de worktrees efímeros), y un pre-chequeo que
descarta candidatos buenos le enseñaría al lazo que todo falla, que es peor que
no tenerlo.

Lo que este módulo NO hace, a propósito: diagnósticos de lenguajes no-Python.
Es la otra mitad de lo que da un LSP, y hoy no tiene a qué apuntar — Atlas
tiene 1 fichero no-Python en ``prototypes/``, ``ui/atlas-shell`` se archivó con
ADR-085 y los forks viven fuera del repo. Construirlo ahora sería un cascarón
esperando una base de código que aún no existe.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Tope para la pasada de tipos. mypy tarda ~250 ms sobre un fichero; esto sólo
#: garantiza que un mypy atascado no se coma la ganancia que este módulo existe
#: para dar.
TYPE_CHECK_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class PrecheckResult:
    """``ok=False`` sólo por sintaxis. Un resultado ``ok=True`` significa "no
    encontré motivo BARATO para descartarlo", nunca "esto está bien": la
    validación de verdad sigue detrás."""

    ok: bool
    stage: str  # "ok" | "syntax"
    detail: str = ""
    type_errors: tuple[str, ...] = field(default_factory=tuple)


def _python_files(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.suffix == ".py" and p.is_file()]


def precheck_files(
    paths: list[Path],
    *,
    repo_root: Path,
    run_types: bool = True,
) -> PrecheckResult:
    """Comprueba lo barato primero. Nunca lanza: en el camino de un lazo
    autónomo, un pre-chequeo que revienta es peor que uno que no encuentra
    nada."""
    candidates = _python_files(paths)
    if not candidates:
        # Ni ficheros Python ni ficheros existentes: no medible, no roto.
        return PrecheckResult(ok=True, stage="ok")

    for path in candidates:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # no medible
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return PrecheckResult(
                ok=False,
                stage="syntax",
                detail=f"{path.name}:{exc.lineno}: {exc.msg}",
            )

    if not run_types:
        return PrecheckResult(ok=True, stage="ok")

    return PrecheckResult(ok=True, stage="ok", type_errors=_type_errors(candidates, repo_root))


def _type_errors(paths: list[Path], repo_root: Path) -> tuple[str, ...]:
    """Errores de tipo como INFORMACIÓN, nunca como veto (ver docstring del
    módulo). Si mypy no está, tarda demasiado o falla por su cuenta, se
    devuelve vacío: no saber no es un hallazgo."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary", *[str(p) for p in paths]],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=TYPE_CHECK_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    return tuple(
        line for line in result.stdout.splitlines() if ": error:" in line
    )
