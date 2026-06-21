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

from atlas.mcp.catalog import CatalogEntry
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
    """Veta un `connect` con SentinelGate pre-spawn (metacaracteres/IOC). Devuelve
    la razón del veto o None si es admisible. noop/place_skill sin comando = None."""
    if action.action != "connect" or not action.command:
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
    """Ejecuta una acción. `connect` se VETA antes de correr; `noop` no hace nada;
    `place_skill` se delega al runner. Devuelve un estado legible."""
    if action.action == "noop":
        return f"{action.name}: served (nada que instalar)"
    veto = vet_action(action, sentinel)
    if veto is not None:
        return f"{action.name}: VETADO ({veto})"
    if action.command is None:
        return f"{action.name}: sin comando — omitido"
    runner(action.command)
    return f"{action.name}: {action.action} OK"
