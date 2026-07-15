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

import http.client
import ipaddress
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import IO

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
from atlas.security.bwrap_jail import BwrapUnavailableError
from atlas.security.sandbox import LayeredIsolationSandbox, SandboxResult
from atlas.security.ssrf_bridge import SSRFBridge


# ---------------------------------------------------------------------------
# Pinned-IP connection helpers (evitar TOCTOU de DNS-rebinding)
# ---------------------------------------------------------------------------
#
# Estrategia: la URL original (con el hostname) se mantiene intacta —
# urllib construye el Request con ella— pero sobreescribimos la capa de
# transporte para que el socket se conecte a la pinned_ip (ya validada)
# en lugar de volver a resolver DNS.  La negociación TLS sigue usando el
# hostname original como server_hostname → check_hostname=True funciona
# y el certificado se valida contra el hostname, no contra la IP.
#
# Para HTTP plano basta con conectar a la IP; el header Host (que urllib
# añade automáticamente desde la URL original) garantiza el vhost routing.


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection que conecta a una IP fijada pero valida TLS contra el hostname."""

    def __init__(self, host: str, port: int | None, *, pinned_ip: str, **kwargs: object) -> None:
        super().__init__(host, port, **kwargs)  # type: ignore[arg-type]
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        # Conectar al socket contra la IP fijada (no hay segunda resolución DNS).
        base: http.client.HTTPConnection = self  # acceso a atributos heredados sin confundir mypy
        src = getattr(base, "source_address", None)
        sock = socket.create_connection(
            (self._pinned_ip, base.port or 443),
            timeout=base.timeout,
            source_address=src,
        )
        # Envolver el socket con TLS usando el hostname original como SNI.
        ctx: ssl.SSLContext = getattr(self, "_context", None) or ssl.create_default_context()
        self.sock = ctx.wrap_socket(sock, server_hostname=base.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection que conecta a una IP fijada (HTTP plano)."""

    def __init__(self, host: str, port: int | None, *, pinned_ip: str, **kwargs: object) -> None:
        super().__init__(host, port, **kwargs)  # type: ignore[arg-type]
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        base: http.client.HTTPConnection = self
        src = getattr(base, "source_address", None)
        self.sock = socket.create_connection(
            (self._pinned_ip, base.port or 80),
            timeout=base.timeout,
            source_address=src,
        )


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            lambda host, **kw: _PinnedHTTPSConnection(host, None, pinned_ip=self._pinned_ip, **kw),
            req,
            context=ssl.create_default_context(),
        )


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            lambda host, **kw: _PinnedHTTPConnection(host, None, pinned_ip=self._pinned_ip, **kw),
            req,
        )

    http_request = urllib.request.AbstractHTTPHandler.do_request_


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Expone las respuestas 30x al executor; nunca sigue saltos por su cuenta."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _build_opener_with_pinned_ip(
    pinned_ip: str | None,
    url: str,
    timeout_s: int,
) -> urllib.request.OpenerDirector:
    """Construye un opener de un solo salto, sin proxy ni redirects automáticos."""
    del timeout_s
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ExecutorError(f"esquema de transporte no permitido: {scheme or '<vacío>'}")

    host = parsed.hostname
    if not host:
        raise ExecutorError("URL de red sin hostname")
    selected_ip = pinned_ip
    if selected_ip is None:
        try:
            ipaddress.ip_address(host)
        except ValueError as exc:
            raise ExecutorError(
                f"SSRF check permitido sin IP fijada para hostname: {host}"
            ) from exc
        selected_ip = host
    try:
        ipaddress.ip_address(selected_ip)
    except ValueError as exc:
        raise ExecutorError(f"IP fijada inválida: {selected_ip}") from exc

    common_handlers: tuple[urllib.request.BaseHandler, ...] = (
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    if scheme == "https":
        return urllib.request.build_opener(
            *common_handlers,
            _PinnedHTTPSHandler(selected_ip),
        )
    return urllib.request.build_opener(
        *common_handlers,
        _PinnedHTTPHandler(selected_ip),
    )


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
    MAX_REDIRECTS = 5
    MAX_REDIRECT_LOCATION_BYTES = 8 * 1024
    REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

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

        req_headers = {
            key: value
            for key, value in (headers or {}).items()
            if key.lower() not in {"host", "proxy-authorization"}
        }
        req_headers.setdefault("User-Agent", "AtlasCore/0.3")

        current_url = cap.url
        current_decision = sink_decision
        redirect_count = 0

        while True:
            # Cada salto usa exclusivamente la IP devuelta por la validación de
            # ese mismo URL. La URL original conserva Host y SNI correctos.
            opener = _build_opener_with_pinned_ip(
                current_decision.pinned_ip,
                current_url,
                timeout_s,
            )
            request = urllib.request.Request(
                current_url,
                data=body,
                method=cap.method,
                headers=req_headers,
            )

            try:
                with opener.open(request, timeout=timeout_s) as resp:
                    response_bytes = resp.read(cap.max_response_bytes + 1)
                    truncated = len(response_bytes) > cap.max_response_bytes
                    if truncated:
                        response_bytes = response_bytes[: cap.max_response_bytes]
                    response_headers = {k: v for k, v in resp.headers.items()}
                    status = resp.getcode() or 0
                break
            except urllib.error.HTTPError as e:
                location = e.headers.get("Location")
                if e.code in self.REDIRECT_STATUS_CODES and location:
                    e.close()
                    if redirect_count >= self.MAX_REDIRECTS:
                        reason = f"demasiados redirects (máximo {self.MAX_REDIRECTS})"
                        self._log_network_failure(cap, reason)
                        raise ExecutorError(reason) from e
                    if cap.method not in {"GET", "HEAD"}:
                        reason = f"redirect no permitido para método {cap.method}"
                        self._log_network_failure(cap, reason)
                        raise ExecutorError(reason) from e
                    if len(location.encode("utf-8")) > self.MAX_REDIRECT_LOCATION_BYTES:
                        reason = "Location de redirect excede el límite permitido"
                        self._log_network_failure(cap, reason)
                        raise ExecutorError(reason) from e

                    next_url = urllib.parse.urljoin(current_url, location)
                    current_scheme = urllib.parse.urlsplit(current_url).scheme.lower()
                    next_scheme = urllib.parse.urlsplit(next_url).scheme.lower()
                    if next_scheme != current_scheme:
                        reason = (
                            "cambio de esquema en redirect bloqueado: "
                            f"{current_scheme} -> {next_scheme or '<vacío>'}"
                        )
                        self._log_network_failure(cap, reason)
                        raise ExecutorError(reason) from e

                    redirect_decision = self._ssrf_bridge.check(next_url)
                    if not redirect_decision.allowed:
                        self._merkle.log(
                            action="network.ssrf_blocked",
                            agent=self.AGENT,
                            result="blocked",
                            risk_level="high",
                            payload={
                                "url": next_url,
                                "source_url": current_url,
                                "stage": "redirect",
                                "reason": redirect_decision.reason,
                            },
                        )
                        raise ExecutorError(
                            f"SSRF bloqueado en redirect: {redirect_decision.reason}"
                        ) from e
                    if redirect_decision.domain.lower() != sink_decision.domain.lower():
                        reason = (
                            "cambio de host en redirect bloqueado por la capability: "
                            f"{sink_decision.domain} -> {redirect_decision.domain}"
                        )
                        self._log_network_failure(cap, reason)
                        raise ExecutorError(reason) from e

                    redirect_count += 1
                    current_url = next_url
                    current_decision = redirect_decision
                    continue

                self._log_network_failure(cap, f"HTTPError {e.code}")
                raise ExecutorError(
                    f"HTTP {e.code} desde {current_url}: {e.reason}"
                ) from e
            except urllib.error.URLError as e:
                self._log_network_failure(cap, str(e))
                raise ExecutorError(f"error de red {current_url}: {e.reason}") from e
            except TimeoutError as e:
                self._log_network_failure(cap, "timeout")
                raise ExecutorError(f"timeout tras {timeout_s}s en {current_url}") from e

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
                "final_url": current_url,
                "redirect_count": redirect_count,
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
        # Si el capability transporta código Python, usamos el jail OS-level
        # (ADR-055). Fail-closed: sin bwrap, la ejecución se rechaza.
        try:
            if cap.code is not None:
                result = self._sandbox.execute_in_jail(
                    cap.code,
                    timeout_s=cap.timeout_s,
                )
            else:
                try:
                    writable, read_only_paths = self._structured_command_scope(cap)
                except ExecutorError as exc:
                    self._merkle.log(
                        action="exec.scope_denied",
                        agent=self.AGENT,
                        result="blocked",
                        risk_level="high",
                        payload={"command": cap.command, "reason": str(exc)},
                    )
                    raise
                full_command = [cap.command, *cap.args]
                result = self._sandbox.execute_command(
                    command=full_command,
                    working_dir=cap.working_dir,
                    timeout_s=cap.timeout_s,
                    working_dir_writable=writable,
                    read_only_paths=read_only_paths,
                )
        except BwrapUnavailableError as exc:
            self._merkle.log(
                action="exec.jail_unavailable",
                agent=self.AGENT,
                result="blocked",
                risk_level="high",
                payload={"command": cap.command, "reason": str(exc)},
            )
            raise ExecutorError(str(exc)) from exc

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

    def _structured_command_scope(
        self, cap: ExecCapability,
    ) -> tuple[bool, tuple[Path, ...]]:
        """Deriva mounts mínimos del capability ya revalidado.

        Todos los comandos son read-only salvo `patch`. Un patch solo obtiene
        escritura sobre su cwd y lectura sobre los ficheros declarados mediante
        `-i/--input`. `git -C` recibe exclusivamente el repo fijado por el perfil.
        """
        read_only: list[Path] = []
        writable = cap.command == "patch"

        if cap.command == "git" and len(cap.args) >= 2 and cap.args[0] == "-C":
            root = self._issuer.profile.git_inspect_root
            requested = Path(cap.args[1]).expanduser().resolve()
            if root is None or requested != root:
                raise ExecutorError("git -C no coincide con git_inspect_root")
            if not root.is_dir():
                raise ExecutorError(f"git_inspect_root no existe: {root}")
            read_only.append(root)

        if cap.command == "patch":
            inputs: list[str] = []
            index = 0
            while index < len(cap.args):
                arg = cap.args[index]
                if arg in {"-i", "--input"}:
                    if index + 1 >= len(cap.args):
                        raise ExecutorError(f"entrada patch incompleta: {arg}")
                    inputs.append(cap.args[index + 1])
                    index += 2
                    continue
                if arg.startswith("--input="):
                    inputs.append(arg.split("=", 1)[1])
                elif arg.startswith("-i") and len(arg) > 2:
                    inputs.append(arg[2:])
                index += 1

            for raw in inputs:
                candidate = Path(raw).expanduser()
                if not candidate.is_absolute():
                    candidate = cap.working_dir / candidate
                try:
                    resolved = candidate.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise ExecutorError(f"entrada patch no existe: {candidate}") from exc
                decision = self._issuer.profile.evaluate_path(str(resolved), write=False)
                if not decision.allowed:
                    raise ExecutorError(f"entrada patch rechazada: {decision.reason}")
                if not resolved.is_file():
                    raise ExecutorError(f"entrada patch no es fichero regular: {resolved}")
                read_only.append(resolved)

        return writable, tuple(dict.fromkeys(read_only))

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
