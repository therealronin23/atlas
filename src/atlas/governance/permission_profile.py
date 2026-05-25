"""
Atlas Core — Permission Profile (ADR-006)
Mapa de carpetas, niveles de permiso y evaluacion de acceso.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class PermissionLevel(str, Enum):
    AUTO    = "auto"     # Ejecuta sin preguntar
    CONFIRM = "confirm"  # Pide confirmacion una vez por sesion
    APPROVE = "approve"  # Aprobacion explicita cada vez
    BLOCKED = "blocked"  # Nunca ejecuta


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    level: PermissionLevel
    reason: str
    path: str


# Subcomandos git permitidos (solo inspeccion read-only). SEC-01.
_GIT_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset({
    "status", "log", "diff", "show", "rev-parse", "branch", "describe", "apply",
})
# Metacaracteres de encadenamiento shell (SEC shell-chain).
_SHELL_CHAIN_PATTERN = re.compile(
    r"(?:[;|]|&&|\|\||`|\$\(|\$\{|<\(|>\(|\n|\r)"
)

_GIT_DENIED_SUBCOMMANDS: frozenset[str] = frozenset({
    "push", "pull", "fetch", "merge", "rebase", "reset", "checkout",
    "commit", "am", "cherry-pick", "revert", "tag", "stash", "clone",
    "remote", "submodule", "worktree",
})


class PermissionProfile:
    """
    Carga permissions.yaml y evalua si una ruta o accion esta permitida.
    Trabaja en terminos de Path absolutos resueltos.
    """

    # Rutas absolutamente bloqueadas — hardcoded, no configurables por el usuario
    _ABSOLUTE_BLOCKS: tuple[str, ...] = (
        ".ssh",
        ".gnupg",
        ".aws",
        "/etc/",
        "/root/",
        "/boot/",
        "/dev/",
    )

    # Rutas del SO con lectura parcial permitida
    _SYSTEM_READ_ALLOWED: tuple[str, ...] = (
        "/sys/class/hwmon/",
    )

    def __init__(self, config_path: Path, workspace: Path | None = None) -> None:
        with config_path.open(encoding="utf-8") as f:
            self._cfg: dict[str, Any] = yaml.safe_load(f)

        self._workspace: Path = workspace or self._resolve_workspace()
        self._confirmed_this_session: set[str] = set()

    # ------------------------------------------------------------------
    # Evaluacion de rutas
    # ------------------------------------------------------------------

    def evaluate_path(self, path: str, write: bool = False) -> AccessDecision:
        """
        Evalua si Atlas puede acceder a `path`.
        `write=True` evalua permisos de escritura; `write=False` de lectura.
        """
        resolved = Path(path).expanduser().resolve()
        str_path = str(resolved)

        # 1. Bloqueo absoluto
        if self._is_absolute_block(resolved):
            return AccessDecision(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason=f"Ruta en lista de bloqueo absoluto: {str_path}",
                path=str_path,
            )

        # 2. Dentro del workspace
        if self._is_inside_workspace(resolved):
            return self._evaluate_workspace_path(resolved, write)

        # 3. Ruta de sistema con lectura parcial
        if not write and self._is_system_read_allowed(str_path):
            return AccessDecision(
                allowed=True,
                level=PermissionLevel.AUTO,
                reason="Lectura de ruta de sistema permitida (Thermal Watchdog).",
                path=str_path,
            )

        # 4. Rutas de lectura extendida
        extended = self._cfg.get("workspace", {}).get("read_extended", [])
        for ext in extended:
            ext_resolved = Path(ext).expanduser().resolve()
            try:
                resolved.relative_to(ext_resolved)
                if write:
                    return AccessDecision(
                        allowed=False,
                        level=PermissionLevel.BLOCKED,
                        reason="Las rutas de lectura extendida son read-only.",
                        path=str_path,
                    )
                return AccessDecision(
                    allowed=True,
                    level=PermissionLevel.CONFIRM,
                    reason=f"Ruta en lectura extendida: {ext}",
                    path=str_path,
                )
            except ValueError:
                continue

        # 5. Fuera de todo alcance
        return AccessDecision(
            allowed=False,
            level=PermissionLevel.BLOCKED,
            reason=f"Ruta fuera del workspace y no en lectura extendida: {str_path}",
            path=str_path,
        )

    def evaluate_shell_command(self, command: str) -> AccessDecision:
        """Evalua si un comando shell esta en la allowlist."""
        cmd_strip = command.strip()

        if _SHELL_CHAIN_PATTERN.search(cmd_strip):
            return AccessDecision(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason="Comando con encadenamiento shell prohibido (; | && || ` $() ).",
                path=cmd_strip,
            )

        # SEC-01: git con subcomandos explicitos; nunca prefix-match sobre "git" a secas.
        if cmd_strip == "git" or cmd_strip.startswith("git "):
            parts = cmd_strip.split()
            if len(parts) < 2:
                return AccessDecision(
                    allowed=False,
                    level=PermissionLevel.BLOCKED,
                    reason="git requiere un subcomando (p. ej. git status).",
                    path=cmd_strip,
                )
            sub = parts[1]
            if sub in _GIT_DENIED_SUBCOMMANDS:
                return AccessDecision(
                    allowed=False,
                    level=PermissionLevel.BLOCKED,
                    reason=f"Subcomando git prohibido: {sub}",
                    path=cmd_strip,
                )
            if sub not in _GIT_ALLOWED_SUBCOMMANDS:
                return AccessDecision(
                    allowed=False,
                    level=PermissionLevel.BLOCKED,
                    reason=f"Subcomando git no permitido: {sub}",
                    path=cmd_strip,
                )
            level = (
                PermissionLevel.CONFIRM
                if sub == "apply"
                else PermissionLevel.AUTO
            )
            return AccessDecision(
                allowed=True,
                level=level,
                reason=f"git {sub} permitido",
                path=cmd_strip,
            )

        allowlist: list[str] = self._cfg.get("shell_allowlist", [])
        for allowed_cmd in allowlist:
            if allowed_cmd.strip() == "git":
                continue
            if cmd_strip == allowed_cmd or cmd_strip.startswith(allowed_cmd + " "):
                return AccessDecision(
                    allowed=True,
                    level=PermissionLevel.CONFIRM,
                    reason=f"Comando en allowlist: {allowed_cmd}",
                    path=cmd_strip,
                )
        return AccessDecision(
            allowed=False,
            level=PermissionLevel.BLOCKED,
            reason=f"Comando no esta en la shell allowlist: {cmd_strip}",
            path=cmd_strip,
        )

    # ------------------------------------------------------------------
    # Sesion de confirmaciones
    # ------------------------------------------------------------------

    def mark_confirmed(self, key: str) -> None:
        """Registra que el usuario confirmo esta herramienta/accion en la sesion."""
        self._confirmed_this_session.add(key)

    def is_confirmed_this_session(self, key: str) -> bool:
        return key in self._confirmed_this_session

    def clear_session(self) -> None:
        self._confirmed_this_session.clear()

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def telegram_config(self) -> dict[str, Any]:
        return self._cfg.get("telegram", {})

    @property
    def shell_allowlist(self) -> list[str]:
        return self._cfg.get("shell_allowlist", [])

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _resolve_workspace(self) -> Path:
        env_home = os.environ.get("ATLAS_HOME")
        if env_home:
            return Path(env_home).expanduser().resolve()
        return Path.home() / "atlas"

    def _is_absolute_block(self, path: Path) -> bool:
        str_path = str(path)
        home = str(Path.home())
        for block in self._ABSOLUTE_BLOCKS:
            if block.startswith("/"):
                if str_path.startswith(block):
                    return True
            else:
                if str_path.startswith(f"{home}/{block}") or f"/{block}/" in str_path:
                    return True
        return False

    def _is_inside_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self._workspace)
            return True
        except ValueError:
            return False

    def _is_system_read_allowed(self, str_path: str) -> bool:
        return any(str_path.startswith(p) for p in self._SYSTEM_READ_ALLOWED)

    def _evaluate_workspace_path(self, path: Path, write: bool) -> AccessDecision:
        str_path = str(path)
        ws_cfg = self._cfg.get("workspace", {})

        if not write:
            return AccessDecision(
                allowed=True,
                level=PermissionLevel.AUTO,
                reason="Lectura dentro del workspace.",
                path=str_path,
            )

        # Escritura en tmp/ → AUTO
        tmp = self._workspace / "tmp"
        try:
            path.relative_to(tmp)
            return AccessDecision(
                allowed=True,
                level=PermissionLevel.AUTO,
                reason="Escritura en workspace/tmp/ (efimera).",
                path=str_path,
            )
        except ValueError:
            pass

        # governance.json → siempre BLOCKED para escritura
        if path == self._workspace / "config" / "governance.json":
            return AccessDecision(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason="governance.json es inmutable.",
                path=str_path,
            )

        # confirm_write
        for rel in ws_cfg.get("confirm_write", []):
            confirm_path = self._workspace / rel
            try:
                path.relative_to(confirm_path)
                return AccessDecision(
                    allowed=True,
                    level=PermissionLevel.CONFIRM,
                    reason=f"Escritura en zona confirm_write: {rel}",
                    path=str_path,
                )
            except ValueError:
                continue

        # Default dentro del workspace → CONFIRM
        return AccessDecision(
            allowed=True,
            level=PermissionLevel.CONFIRM,
            reason="Escritura dentro del workspace (zona no catalogada, CONFIRM por defecto).",
            path=str_path,
        )
