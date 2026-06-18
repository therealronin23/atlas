"""
Atlas Core — AtlasExecutor (ADR-020)

Ejecutor unificado que solo acepta capability tokens. Garantiza que
toda operacion con efecto externo (leer fichero, escribir, request
HTTP, ejecutar comando) ha sido pre-validada y queda registrada en
el Merkle Logger.

Capa final de defensa antes del IO real. El AST Guard se invoca como
backstop cuando la capability transporta codigo Python a ejecutar.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ast_guard import ASTGuard
from atlas.security.generated_code_policy import GeneratedCodePolicy
from atlas.governance.permission_profile import PermissionLevel
from atlas.security.capabilities import (
    CapabilityIssuer,
    ExecCapability,
    NetworkCapability,
    ReadCapability,
    WriteCapability,
)
from atlas.security.sandbox import LayeredIsolationSandbox, SandboxResult
from atlas.security.ssrf_bridge import SSRFBridge


# ---------------------------------------------------------------------------
# Errores y resultados
# ---------------------------------------------------------------------------


class ExecutorError(Exception):
    """Fallo en runtime (IO real, timeout, etc.). La capability era valida."""


@dataclass(frozen=True)
class NetworkResponse:
    status_code: int
    body: bytes
    headers: dict[str, str]
    truncated: bool


# ---------------------------------------------------------------------------
# AtlasExecutor
# ---------------------------------------------------------------------------


class AtlasExecutor:
    """
    Ejecuta acciones representadas por capability tokens. No acepta paths
    ni URLs sueltas — solo tokens emitidos por CapabilityIssuer.
    """

    AGENT = "atlas.executor"

    def __init__(
        self,
        issuer: CapabilityIssuer,
        merkle: MerkleLogger,
        sandbox: LayeredIsolationSandbox,
        ast_guard: ASTGuard | None = None,
        ssrf_bridge: SSRFBridge | None = None,
    ) -> None:
        self._issuer = issuer
        self._merkle = merkle
        self._sandbox = sandbox
        self._ast_guard = ast_guard or ASTGuard()
        # Defensive re-check at the sink — reuses the issuer's bridge when not
        # explicitly provided (avoids a second allowlist definition).
        self._ssrf_bridge: SSRFBridge = ssrf_bridge or issuer.bridge

    @property
    def issuer(self) -> CapabilityIssuer:
        return self._issuer

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def execute_read(self, cap: ReadCapability) -> bytes:
        if not isinstance(cap, ReadCapability):
            raise ExecutorError(f"execute_read espera ReadCapability, recibio {type(cap).__name__}")
        self._require_permission_cleared(cap)

        try:
            if not cap.path.exists():
                raise ExecutorError(f"ruta no existe: {cap.path}")
            if not cap.path.is_file():
                raise ExecutorError(f"no es un fichero regular: {cap.path}")

            size = cap.path.stat().st_size
            truncated = size > cap.max_bytes
            with cap.path.open("rb") as f:
                data = f.read(cap.max_bytes)
        except OSError as e:
            self._log_io_failure("file.read", cap.path, str(e))
            raise ExecutorError(f"error leyendo {cap.path}: {e}") from e

        self._merkle.log(
            action="file.read",
            agent=self.AGENT,
            result="ok",
            risk_level="safe",
            payload={
                "path": str(cap.path),
                "bytes_read": len(data),
                "truncated": truncated,
                "max_bytes": cap.max_bytes,
                "level": cap.level.value,
            },
        )
        return data

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------

    def execute_write(self, cap: WriteCapability, data: bytes) -> int:
        if not isinstance(cap, WriteCapability):
            raise ExecutorError(f"execute_write espera WriteCapability, recibio {type(cap).__name__}")
        self._require_permission_cleared(cap)
        if not isinstance(data, (bytes, bytearray)):
            raise ExecutorError(f"data debe ser bytes, recibio {type(data).__name__}")
        if len(data) > cap.max_bytes:
            raise ExecutorError(f"data ({len(data)}B) excede max_bytes ({cap.max_bytes}B)")

        try:
            cap.path.parent.mkdir(parents=True, exist_ok=True)
            mode = "ab" if cap.append else "wb"
            with cap.path.open(mode) as f:
                bytes_written = f.write(data)
        except OSError as e:
            self._log_io_failure("file.write", cap.path, str(e))
            raise ExecutorError(f"error escribiendo {cap.path}: {e}") from e

        self._merkle.log(
            action="file.write",
            agent=self.AGENT,
            result="ok",
            risk_level="medium" if cap.level.value in ("confirm", "approve") else "safe",
            payload={
                "path": str(cap.path),
                "bytes_written": bytes_written,
                "append": cap.append,
                "level": cap.level.value,
            },
        )
        return bytes_written

    # ------------------------------------------------------------------
    # NETWORK
    # ------------------------------------------------------------------

    def execute_network(
        self,
        cap: NetworkCapability,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout_s: int = 30,
    ) -> NetworkResponse:
        if not isinstance(cap, NetworkCapability):
            raise ExecutorError(f"execute_network espera NetworkCapability, recibio {type(cap).__name__}")
        self._require_permission_cleared(cap)

        # Defensive re-validation at the sink: the capability may have been
        # constructed directly (without issuer) or the blocklist may have been
        # updated after issue time.  Abort early — before any socket activity.
        sink_decision = self._ssrf_bridge.check(cap.url)
        if not sink_decision.allowed:
            self._merkle.log(
                action="network.ssrf_blocked",
                agent=self.AGENT,
                result="blocked",
                risk_level="high",
                payload={"url": cap.url, "reason": sink_decision.reason},
            )
            raise ExecutorError(
                f"SSRF check bloqueado en el sink: {sink_decision.reason}"
            )

        req_headers = dict(headers or {})
        req_headers.setdefault("User-Agent", "AtlasCore/0.3")

        request = urllib.request.Request(
            cap.url,
            data=body,
            method=cap.method,
            headers=req_headers,
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as resp:
                response_bytes = resp.read(cap.max_response_bytes + 1)
                truncated = len(response_bytes) > cap.max_response_bytes
                if truncated:
                    response_bytes = response_bytes[: cap.max_response_bytes]
                response_headers = {k: v for k, v in resp.headers.items()}
                status = resp.getcode() or 0
        except urllib.error.HTTPError as e:
            # HTTP error con respuesta — log + raise como ExecutorError
            self._log_network_failure(cap, f"HTTPError {e.code}")
            raise ExecutorError(f"HTTP {e.code} desde {cap.url}: {e.reason}") from e
        except urllib.error.URLError as e:
            self._log_network_failure(cap, str(e))
            raise ExecutorError(f"error de red {cap.url}: {e.reason}") from e
        except TimeoutError as e:
            self._log_network_failure(cap, "timeout")
            raise ExecutorError(f"timeout tras {timeout_s}s en {cap.url}") from e

        self._merkle.log(
            action="network.request",
            agent=self.AGENT,
            result="ok",
            risk_level="medium",
            payload={
                "url": cap.url,
                "domain": cap.domain,
                "method": cap.method,
                "status_code": status,
                "bytes_received": len(response_bytes),
                "truncated": truncated,
            },
        )
        return NetworkResponse(
            status_code=status,
            body=response_bytes,
            headers=response_headers,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # EXEC
    # ------------------------------------------------------------------

    def execute_exec(self, cap: ExecCapability) -> SandboxResult:
        if not isinstance(cap, ExecCapability):
            raise ExecutorError(f"execute_exec espera ExecCapability, recibio {type(cap).__name__}")
        self._require_permission_cleared(cap)

        # Defensive re-validation: check cap.command against the permission
        # profile at the sink.  Catches capabilities constructed directly
        # (bypassing the issuer) or profile changes since issue time.
        full_cmd = f"{cap.command} {' '.join(cap.args)}" if cap.args else cap.command
        sink_cmd_decision = self._issuer.profile.evaluate_shell_command(full_cmd)
        if not sink_cmd_decision.allowed:
            self._merkle.log(
                action="exec.permission_denied",
                agent=self.AGENT,
                result="blocked",
                risk_level="high",
                payload={"command": full_cmd, "reason": sink_cmd_decision.reason},
            )
            raise ExecutorError(
                f"Comando rechazado en re-validacion del sink: {sink_cmd_decision.reason}"
            )

        # Si la capability transporta codigo Python, validar con AST Guard
        # antes de pasarlo a la sandbox (ultima linea de defensa).
        if cap.code is not None:
            policy = GeneratedCodePolicy(self._ast_guard)
            check = policy.check_generated_source(cap.code)
            if not check.passed:
                self._merkle.log(
                    action="exec.ast_guard_rejected",
                    agent=self.AGENT,
                    result="blocked",
                    risk_level="high",
                    payload={
                        "command": cap.command,
                        "violations": list(check.violations),
                    },
                )
                raise ExecutorError(
                    f"Generated code policy rechazo el codigo: {check.reason}"
                )

        # Delegamos al sandbox para la ejecucion fisica.
        # El sandbox tiene su propio AST Guard interno cuando se invoca
        # execute(code=...). El chequeo de arriba es defensivo (idempotente).
        if cap.code is not None:
            result = self._sandbox.execute(
                code=cap.code,
                working_dir=cap.working_dir,
                timeout_s=cap.timeout_s,
            )
        else:
            full_command = [cap.command, *cap.args]
            result = self._sandbox.execute_command(
                command=full_command,
                working_dir=cap.working_dir,
                timeout_s=cap.timeout_s,
            )

        self._merkle.log(
            action="exec.command",
            agent=self.AGENT,
            result="ok" if result.success else "failed",
            risk_level="medium",
            payload={
                "command": cap.command,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "working_dir": str(cap.working_dir),
                "with_code": cap.code is not None,
                "level": cap.level.value,
                "requested_timeout_s": cap.timeout_s,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _log_io_failure(self, action: str, path: Path, error: str) -> None:
        self._merkle.log(
            action=action,
            agent=self.AGENT,
            result="failed",
            risk_level="medium",
            payload={"path": str(path), "error": error},
        )

    def _log_network_failure(self, cap: NetworkCapability, error: str) -> None:
        self._merkle.log(
            action="network.request",
            agent=self.AGENT,
            result="failed",
            risk_level="medium",
            payload={"url": cap.url, "domain": cap.domain, "error": error},
        )

    def _session_key(self, cap: ReadCapability | WriteCapability | NetworkCapability | ExecCapability) -> str:
        if isinstance(cap, ExecCapability):
            args = " ".join(cap.args)
            return f"exec:{cap.command} {args}".strip()
        if isinstance(cap, WriteCapability):
            return f"write:{cap.path}"
        if isinstance(cap, ReadCapability):
            return f"read:{cap.path}"
        return f"network:{cap.url}"

    def _require_permission_cleared(
        self,
        cap: ReadCapability | WriteCapability | NetworkCapability | ExecCapability,
    ) -> None:
        if cap.level == PermissionLevel.AUTO:
            return
        profile = self._issuer.profile
        key = self._session_key(cap)
        if profile.is_confirmed_this_session(key):
            return
        clearance = getattr(cap, "clearance", None)
        if clearance and profile.is_confirmed_this_session(clearance):
            return
        if cap.level == PermissionLevel.CONFIRM:
            raise ExecutorError(
                f"Requiere confirmacion de sesion para: {key}. "
                "Use mark_confirmed() tras aprobacion o confirmacion del usuario."
            )
        if cap.level == PermissionLevel.APPROVE:
            raise ExecutorError(
                f"Requiere aprobacion explicita para: {key}."
            )
        raise ExecutorError(f"Permiso bloqueado: {key}")
