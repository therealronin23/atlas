"""Sondas VIVAS para `atlas reality` y clasificación honesta de la evidencia.

``reality.py`` nació midiendo dos cosas que se parecen a la realidad sin serlo:
**configuración** (variables de entorno, ficheros de settings) e **historia**
(artefactos que un proceso anterior dejó en disco). Ninguna de las dos responde
a la pregunta que importa — *¿esto funciona AHORA?* — y la diferencia dejó de
ser académica el día que ``atlas-core.service`` estuvo 23 h muerto mientras el
informe seguía en verde, porque todo lo que miraba eran ficheros del pasado.

Este módulo aporta lo que faltaba:

* **sondas vivas** que interrogan al sistema en el momento (empezando por el
  propio daemon, que era el punto ciego más caro);
* una **clase de evidencia** por sección, para que ``configured=True`` no pueda
  volver a leerse como "funciona".

Las sondas son *fail-honest* por diseño: cuando algo no se puede medir el
resultado es ``None`` (desconocido), jamás ``False``. Confundir "no lo sé" con
"está roto" fabrica alarmas, y la orden del operador fue "sólo lo grave".
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: Interroga al sistema en el momento de preguntar. Es la única clase que
#: puede respaldar una afirmación en presente.
EVIDENCE_LIVE = "live"

#: Lee ajustes: variables de entorno, ficheros de configuración. Prueba que
#: algo está *declarado*, nunca que funcione.
EVIDENCE_CONFIG = "config"

#: Lee lo que otro proceso dejó escrito. Fue verdad cuando se escribió; el
#: informe no sabe si sigue siéndolo.
EVIDENCE_HISTORY = "history"

DEFAULT_UNIT = "atlas-core.service"

#: Claves del informe que NO son secciones-sonda sino contenedores o resúmenes.
#: Marcarlas fue un fallo real y caro de leer: sellar ``checks`` (que es un dict
#: de resultados de comandos) le metía dentro una clave ``evidence``, con lo que
#: dejaba de estar vacío y el renderizador del CLI lo recorría como si cada
#: entrada fuese un check — ``atlas reality`` reventaba con TypeError.
NOT_A_PROBE = frozenset({"checks", "capabilities", "evidence_summary"})

_Runner = Callable[..., Any]


def _systemctl(*args: str, runner: _Runner | None = None) -> str | None:
    """Devuelve stdout, o ``None`` si systemd no es interrogable aquí."""
    run = runner or subprocess.run
    try:
        result = run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stdout = getattr(result, "stdout", None)
    return stdout if isinstance(stdout, str) else None


def daemon_state(
    *, unit: str = DEFAULT_UNIT, runner: _Runner | None = None
) -> dict[str, Any]:
    """¿Está vivo el daemon AHORA?

    La pregunta que ``reality`` nunca hacía. `systemctl is-active` no necesita
    que el daemon coopere — si estuviera colgado, un latido escrito por él
    mismo mentiría; esto no.
    """
    stdout = _systemctl("is-active", unit, runner=runner)
    if stdout is None:
        return {
            "unit": unit,
            "active": None,
            "evidence": EVIDENCE_LIVE,
            "reason": "systemctl no disponible: estado del daemon DESCONOCIDO",
        }
    state = stdout.strip()
    if state == "active":
        return {
            "unit": unit,
            "active": True,
            "evidence": EVIDENCE_LIVE,
            "reason": f"{unit} activo",
        }
    return {
        "unit": unit,
        "active": False,
        "evidence": EVIDENCE_LIVE,
        "reason": f"{unit} NO activo (estado={state or 'desconocido'})",
    }


#: Sondear un Hermes remoto exigiría salir a la red. `atlas reality` se invoca
#: constantemente (AGENTS.md lo manda correr antes de afirmar cualquier estado)
#: y un comando de estado que abre conexiones por su cuenta es una sorpresa
#: desagradable. El tablero LOCAL, en cambio, es una lectura de fichero.
_PROBEABLE_HERMES_MODES = frozenset({"kanban_local", "local_takeover"})


def hermes_probe(
    state: dict[str, Any], *, reachable: Callable[[], bool] | None = None
) -> dict[str, Any]:
    """Convierte `live_verified` de constante en medición.

    Estaba clavado a ``False``: no había ninguna entrada capaz de ponerlo a
    ``True``, así que el campo no informaba de nada. Mientras tanto el tablero
    local respondía con 19 tareas en cola y el informe seguía pidiendo "una
    delegación para tener evidencia de runtime".

    ``reachable`` se inyecta para poder probar los cuatro caminos sin montar un
    tablero; por defecto usa el mismo ``KanbanBridge.reachable()`` que ya
    interroga ``atlas doctor`` — una sonda, no dos.
    """
    probed = dict(state)
    if probed.get("mode") not in _PROBEABLE_HERMES_MODES:
        probed["reachable"] = None
        probed["live_verified"] = False
        probed["evidence"] = EVIDENCE_CONFIG
        return probed

    if reachable is None:
        reachable = _default_hermes_reachable

    probed["evidence"] = EVIDENCE_LIVE
    try:
        alive = bool(reachable())
    except Exception:  # noqa: BLE001 — no medible jamás es "roto"
        probed["reachable"] = None
        probed["live_verified"] = False
        probed["reason"] = "tablero Hermes no interrogable: estado DESCONOCIDO"
        return probed

    probed["reachable"] = alive
    probed["live_verified"] = alive
    probed["reason"] = (
        "tablero Hermes local responde AHORA (sonda viva)"
        if alive
        else "tablero Hermes local NO responde"
    )
    return probed


def _default_hermes_reachable() -> bool:
    from atlas.hermes.kanban_bridge import KanbanBridge

    return bool(KanbanBridge().reachable())


def security_state(root: Path) -> dict[str, Any]:
    """Higiene del fichero de secretos, medida en disco AHORA.

    El operador pidió que ``reality`` mirara también a la seguridad. Nadie en
    el repo comprobaba dos cosas que se contestan con `stat` y `git ls-files`,
    sin coste ni red:

    * si ``.env`` es legible por todo el mundo;
    * si git lo está SIGUIENDO, que es el desastre de verdad — un `git push` y
      las credenciales del operador salen del ordenador.

    No juzga el contenido: eso exigiría leer los secretos, y una herramienta de
    estado no tiene por qué hacerlo.
    """
    env_path = root / ".env"
    gate = os.environ.get("ATLAS_SECURITY_COUNCIL_GATE", "").strip() == "1"
    state: dict[str, Any] = {
        "secrets_path": str(env_path),
        "secrets_present": env_path.is_file(),
        "secrets_mode": None,
        "secrets_world_readable": None,
        "secrets_tracked_by_git": None,
        "council_gate_enabled": gate,  # ajuste declarado (ADR-077), no medición
        "evidence": EVIDENCE_LIVE,
    }

    if not env_path.is_file():
        state["status"] = "unknown"
        state["reason"] = "no hay .env que auditar en este checkout"
        return state

    problems: list[str] = []
    try:
        mode = env_path.stat().st_mode & 0o777
    except OSError:
        state["status"] = "unknown"
        state["reason"] = ".env presente pero no se pudo leer su modo"
        return state

    state["secrets_mode"] = f"{mode:03o}"
    # `otros` o `grupo` con cualquier permiso: en una máquina compartida eso
    # basta para llevarse las claves.
    exposed = bool(mode & 0o077)
    state["secrets_world_readable"] = exposed
    if exposed:
        problems.append(f".env con permisos {mode:03o} (debería ser 600)")

    tracked = _git_tracks(root, ".env")
    state["secrets_tracked_by_git"] = tracked
    if tracked:
        problems.append("git SIGUE a .env: un push publica las credenciales")

    state["status"] = "degraded" if problems else "ok"
    state["reason"] = "; ".join(problems) if problems else ".env sólo legible por su dueño y fuera de git"
    return state


def _git_tracks(root: Path, relative: str) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def evidence_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Cuántas secciones miden el presente, cuántas sólo lo declaran o recuerdan.

    Convierte *"reality no hace nada"* de opinión en número, y en un número que
    no puede empeorar en silencio: una sección nueva sin clase declarada
    aparece en ``unclassified`` en vez de colarse como aprobada.
    """
    counts = {EVIDENCE_LIVE: 0, EVIDENCE_CONFIG: 0, EVIDENCE_HISTORY: 0}
    unclassified: list[str] = []
    for name, section in report.items():
        if not isinstance(section, dict) or name in NOT_A_PROBE:
            continue
        klass = section.get("evidence")
        if klass in counts:
            counts[str(klass)] += 1
        else:
            unclassified.append(name)
    return {
        "live": counts[EVIDENCE_LIVE],
        "config": counts[EVIDENCE_CONFIG],
        "history": counts[EVIDENCE_HISTORY],
        "total_classified": sum(counts.values()),
        "unclassified": len(unclassified),
        "unclassified_sections": sorted(unclassified),
    }
