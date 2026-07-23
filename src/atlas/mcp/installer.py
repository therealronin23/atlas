"""
Atlas Core — Instalador por `mode` (C pasos 5-6).

Planifica la instalación SOLO de lo `verificado` (wire-before-claim) y la enruta
por modo operativo:
  - served    → noop (lo sirve el tronco; nada que bajar).
  - connected → connect (comando de `install`), VETADO por SentinelGate pre-spawn.
  - installed → place_skill (colocar en dir; solo si no se sirve).

La EJECUCIÓN real (correr el comando / copiar) se inyecta como `runner` para no
disparar efectos en tests. Honesto: con 0 `verificado`, el plan está vacío.

Diseño: docs/design/mcp_sector_architecture_audit.md (paso 6).
"""

from __future__ import annotations

import shlex
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from atlas.mcp.catalog import CatalogEntry, load_catalog
from atlas.mcp.config import McpServerConfig
from atlas.security.sentinel_gate import SentinelGate

_MODE_ACTION = {"served": "noop", "connected": "connect", "installed": "place_skill"}


@dataclass(frozen=True)
class InstallAction:
    name: str
    mode: str
    action: str               # noop | connect | place_skill
    command: list[str] | None
    note: str


def plan_install(entries: list[CatalogEntry]) -> list[InstallAction]:
    """Plan de instalación de lo `verificado`, enrutado por mode."""
    out: list[InstallAction] = []
    for e in entries:
        if e.status != "verificado":
            continue
        action = _MODE_ACTION.get(e.mode, "noop")
        command = shlex.split(e.install) if (action != "noop" and e.install.strip()) else None
        out.append(InstallAction(name=e.name, mode=e.mode, action=action,
                                 command=command, note=e.purpose))
    return out


def vet_action(action: InstallAction, sentinel: SentinelGate | None = None) -> str | None:
    """Veta CUALQUIER acción con comando (connect a un MCP o place_skill que instala
    código de terceros) con SentinelGate pre-ejecución (metacaracteres/IOC). Devuelve
    la razón del veto o None si es admisible. Acciones sin comando = None."""
    if not action.command:
        return None
    # vet_command solo escanea el argv (metachars/IOC); snapshot_dir no se usa aquí.
    gate = sentinel if sentinel is not None else SentinelGate(Path(tempfile.gettempdir()))
    cfg = McpServerConfig(name=action.name, cmd=action.command)
    return gate.vet_command(cfg)


def execute(
    action: InstallAction,
    *,
    runner: Callable[[list[str]], None],
    sentinel: SentinelGate | None = None,
) -> str:
    """Fail closed until a future admission executor binds staging to Merkle/HITL.

    An argv that passes ``SentinelGate`` proves only that it lacks known command
    smuggling patterns. It does not prove which bytes a package manager will
    fetch or that a human approved their activation, so direct execution is
    intentionally disabled in A2.
    """
    if action.action == "noop":
        return f"{action.name}: served (nada que instalar)"
    veto = vet_action(action, sentinel)
    if veto is not None:
        return f"{action.name}: VETADO ({veto})"
    return (
        f"{action.name}: BLOQUEADO (instalación directa deshabilitada; "
        "requiere staging + admisión + Merkle/HITL)"
    )


@dataclass(frozen=True)
class InstallReport:
    """Resumen del ensamblaje completo catálogo→plan→veto→execute (wire-before-claim).

    ``installed`` hoy solo cubre acciones ``noop`` (mode=served: nada que bajar,
    ya lo sirve el tronco) — ``execute()`` nunca ejecuta un ``runner`` real para
    connect/place_skill (ver su docstring: fail-closed hasta que exista un
    ejecutor de admisión que ligue staging a Merkle/HITL). Las acciones que
    pasan el veto pero no se ejecutan de verdad se reportan en ``omitted`` con
    la razón explícita del bloqueo — nunca como instaladas.
    """

    installed: tuple[str, ...] = ()
    vetoed: tuple[str, ...] = ()
    omitted: tuple[str, ...] = ()
    total_entries: int = 0
    total_verified: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "instaladas": list(self.installed),
            "vetadas": list(self.vetoed),
            "omitidas": list(self.omitted),
            "total_entries": self.total_entries,
            "total_verificado": self.total_verified,
        }


def run_catalog_install(
    catalog_path: Path,
    *,
    runner: Callable[[list[str]], None] | None = None,
    sentinel: SentinelGate | None = None,
) -> InstallReport:
    """Ensambla el camino completo end-to-end: carga el catálogo real, planifica
    SOLO lo `verificado` (plan_install ya descarta todo lo demás), veta cada
    acción con comando (vet_action/SentinelGate) y, para las que pasan el veto,
    invoca execute() — que hoy sigue fail-closed sin ejecutor de admisión real
    (ver docstring de execute()). Ninguna entrada NO-verificado llega nunca a
    vet_action/execute: plan_install ya las excluyó del plan.

    No finge instalación real: con el `runner` de hoy, ninguna acción con
    comando llega a ejecutarse — se reporta en `omitted` con la razón exacta
    (VETADO o BLOQUEADO), nunca en `installed`.
    """
    entries = load_catalog(catalog_path)
    plan = plan_install(entries)
    _runner: Callable[[list[str]], None] = runner if runner is not None else (lambda cmd: None)

    installed: list[str] = []
    vetoed: list[str] = []
    omitted: list[str] = []

    for action in plan:
        if action.action == "noop":
            installed.append(execute(action, runner=_runner, sentinel=sentinel))
            continue
        veto = vet_action(action, sentinel)
        if veto is not None:
            vetoed.append(f"{action.name}: VETADO ({veto})")
            continue
        # Pasó el veto (argv limpio). execute() decide la ejecución real y hoy
        # sigue fail-closed (sin ejecutor de admisión) — se reporta como
        # omitida con el motivo exacto, nunca como instalada de verdad.
        omitted.append(execute(action, runner=_runner, sentinel=sentinel))

    not_verified = len(entries) - len(plan)
    if not_verified:
        omitted.append(f"{not_verified} entrada(s) no `verificado` (fuera del plan, nunca vetadas/ejecutadas)")

    return InstallReport(
        installed=tuple(installed),
        vetoed=tuple(vetoed),
        omitted=tuple(omitted),
        total_entries=len(entries),
        total_verified=len(plan),
    )
