"""
Atlas Core — Capability Tokens (ADR-020)

Tokens inmutables que representan permiso pre-validado para una accion
concreta. Una capability solo se construye via CapabilityIssuer; el
constructor directo de las clases queda disponible para tests y para
codigo de la libreria pero el contrato es que la validacion ocurre en
issue_*.

Disena del flujo:

    intent -> Classifier -> issuer.issue_X(args) -> Capability(frozen)
                                                          |
                                                          v
                                              AtlasExecutor.execute_X(cap)

Una vez tienes el token, ya esta pre-validado contra:
  - PermissionProfile (ADR-006: workspace, blocked paths, confirm zones)
  - SSRFBridge (egress allowlist)
  - shell allowlist (permissions.yaml)

El executor todavia hace chequeos de runtime (existencia, tamano real,
errores de IO) pero la _intencion_ es imposible de torcer porque viene
encapsulada en un tipo concreto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from atlas.governance.permission_profile import (
    AccessDecision,
    PermissionLevel,
    PermissionProfile,
)
from atlas.security.ssrf_bridge import BridgeDecision, SSRFBridge


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class CapabilityDenied(Exception):
    """
    Se eleva cuando el issuer rechaza emitir una capability por permisos.
    Lleva el AccessDecision o BridgeDecision original para auditoria.
    """

    def __init__(self, reason: str, decision: AccessDecision | BridgeDecision | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.decision = decision


# ---------------------------------------------------------------------------
# Token base + tokens concretos (frozen)
# ---------------------------------------------------------------------------


class _BaseCapability(BaseModel):
    """Base inmutable. arbitrary_types_allowed permite Path."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


DEFAULT_MAX_READ_BYTES: int = 10 * 1024 * 1024     # 10 MB
DEFAULT_MAX_WRITE_BYTES: int = 10 * 1024 * 1024    # 10 MB
DEFAULT_MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024 # 10 MB
DEFAULT_EXEC_TIMEOUT_S: int = 30


class ReadCapability(_BaseCapability):
    """Permiso para leer hasta `max_bytes` bytes de `path`."""

    path: Path
    max_bytes: int = DEFAULT_MAX_READ_BYTES
    level: PermissionLevel = PermissionLevel.AUTO


class WriteCapability(_BaseCapability):
    """Permiso para escribir hasta `max_bytes` bytes en `path`."""

    path: Path
    max_bytes: int = DEFAULT_MAX_WRITE_BYTES
    append: bool = False
    level: PermissionLevel = PermissionLevel.CONFIRM


class NetworkCapability(_BaseCapability):
    """Permiso para hacer una request HTTP/S al dominio resuelto por url."""

    url: str
    method: Literal["GET", "POST", "HEAD", "PUT", "DELETE"] = "GET"
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    domain: str
    level: PermissionLevel = PermissionLevel.AUTO


class ExecCapability(_BaseCapability):
    """
    Permiso para ejecutar `command` con `args` durante <= timeout_s.

    Si `code` no es None, es codigo Python que debe pasar AST Guard
    antes de ejecutarse. En ese caso `command` debe ser el interprete
    que el executor invoca con el codigo via stdin/argv.
    """

    command: str
    args: tuple[str, ...] = ()
    working_dir: Path
    timeout_s: int = DEFAULT_EXEC_TIMEOUT_S
    code: str | None = None
    level: PermissionLevel = PermissionLevel.CONFIRM


# ---------------------------------------------------------------------------
# Issuer — fabrica de capabilities con validacion
# ---------------------------------------------------------------------------


class CapabilityIssuer:
    """
    Emite capabilities solo tras validar contra PermissionProfile y SSRFBridge.
    No tiene estado mutable mas alla del cache de "confirmaciones por sesion"
    que ya vive en PermissionProfile.
    """

    def __init__(self, profile: PermissionProfile, bridge: SSRFBridge | None = None) -> None:
        self._profile = profile
        self._bridge = bridge or SSRFBridge()

    # -- READ -------------------------------------------------------------

    def issue_read(
        self,
        path: Path | str,
        *,
        max_bytes: int = DEFAULT_MAX_READ_BYTES,
    ) -> ReadCapability:
        decision = self._profile.evaluate_path(str(path), write=False)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason, decision)
        if max_bytes <= 0:
            raise CapabilityDenied(f"max_bytes invalido: {max_bytes}")
        return ReadCapability(
            path=Path(decision.path),
            max_bytes=max_bytes,
            level=decision.level,
        )

    # -- WRITE ------------------------------------------------------------

    def issue_write(
        self,
        path: Path | str,
        *,
        max_bytes: int = DEFAULT_MAX_WRITE_BYTES,
        append: bool = False,
    ) -> WriteCapability:
        decision = self._profile.evaluate_path(str(path), write=True)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason, decision)
        if max_bytes <= 0:
            raise CapabilityDenied(f"max_bytes invalido: {max_bytes}")
        return WriteCapability(
            path=Path(decision.path),
            max_bytes=max_bytes,
            append=append,
            level=decision.level,
        )

    # -- NETWORK ----------------------------------------------------------

    def issue_network(
        self,
        url: str,
        *,
        method: Literal["GET", "POST", "HEAD", "PUT", "DELETE"] = "GET",
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> NetworkCapability:
        decision = self._bridge.check(url)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason, decision)
        if max_response_bytes <= 0:
            raise CapabilityDenied(f"max_response_bytes invalido: {max_response_bytes}")
        return NetworkCapability(
            url=url,
            method=method,
            max_response_bytes=max_response_bytes,
            domain=decision.domain,
            level=PermissionLevel.AUTO,
        )

    # -- EXEC -------------------------------------------------------------

    def issue_exec(
        self,
        command: str,
        *,
        args: tuple[str, ...] = (),
        working_dir: Path | str | None = None,
        timeout_s: int = DEFAULT_EXEC_TIMEOUT_S,
        code: str | None = None,
    ) -> ExecCapability:
        # Evaluar contra la allowlist con el comando + args completos para
        # respetar entradas multi-palabra como "git status" o "python3 -m pytest".
        # evaluate_shell_command hace prefix matching, asi que "git status --short"
        # casa con "git status" pero no con "git push".
        full_cmd = f"{command} {' '.join(args)}" if args else command
        decision = self._profile.evaluate_shell_command(full_cmd)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason, decision)
        if timeout_s <= 0 or timeout_s > 600:
            raise CapabilityDenied(f"timeout_s fuera de rango (1-600s): {timeout_s}")

        wd = Path(working_dir) if working_dir else self._profile.workspace / "tmp"
        # working_dir tambien debe ser un path permitido para escritura
        wd_decision = self._profile.evaluate_path(str(wd), write=True)
        if not wd_decision.allowed:
            raise CapabilityDenied(
                f"working_dir rechazado: {wd_decision.reason}",
                wd_decision,
            )

        return ExecCapability(
            command=command,
            args=args,
            working_dir=Path(wd_decision.path),
            timeout_s=timeout_s,
            code=code,
            level=decision.level,
        )

    # ---------------------------------------------------------------------
    # Acceso a las dependencias subyacentes (uso interno del executor)
    # ---------------------------------------------------------------------

    @property
    def profile(self) -> PermissionProfile:
        return self._profile

    @property
    def bridge(self) -> SSRFBridge:
        return self._bridge
