"""Transporte JSON-RPC 2.0 para clientes MCP.

ADR-035 dec.1/2: stdio con stdlib (subprocess + json) tras una interfaz
``McpTransport``. Cubre Calendar/n8n y otros servidores stdio; un
``SdkTransport`` futuro (dep `mcp` opcional) cabe drop-in si aparece
necesidad de HTTP/SSE.

Sin deps nuevas. Sin red. El proceso del server vive fuera del sandbox de
Atlas — es responsabilidad del Registry (config + egress) acotarlo.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import threading
import time
from typing import Any, Protocol

from atlas.security.process_hardening import apply_in_child


class McpProtocolError(RuntimeError):
    """Error de protocolo JSON-RPC / MCP (mensaje malformado, error del server)."""


class McpTransport(Protocol):
    """Contrato del transporte. Síncrono request/response; el server vive
    como subproceso o conexión persistente. ``close()`` libera recursos."""

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any: ...
    def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...
    def close(self) -> None: ...


class StdioTransport:
    """JSON-RPC 2.0 sobre stdin/stdout de un subproceso.

    Mensajes delimitados por una línea por mensaje (formato simple JSON-RPC,
    suficiente para los servers MCP actuales que siguen el line-delimited
    framing; si en el futuro aparecen servers con framing LSP-style con
    ``Content-Length``, ese parser cabe como variante).
    """

    def __init__(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._cmd = list(cmd)
        self._env = dict(env) if env else None
        self._cwd = cwd
        self._timeout = float(timeout_seconds)
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._buf = ""  # líneas no consumidas (leemos por fd con os.read)

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._proc is not None:
            return
        def _set_limits() -> None:
            # nproc=None: RLIMIT_NPROC es por-usuario; un server MCP legítimo
            # (node/uv) necesita crear hilos y el cap absoluto lo mataría
            # (EAGAIN) en un host con miles de hilos vivos. El resto del
            # hardening (AS/CPU/FSIZE/NOFILE/no-new-privs) se mantiene.
            apply_in_child(nproc=None)

        self._proc = subprocess.Popen(  # noqa: S603 — cmd viene de config controlada
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
            cwd=self._cwd,
            text=True,
            bufsize=1,  # line-buffered
            preexec_fn=_set_limits,
            start_new_session=True,
        )

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError:
                proc.terminate()
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                proc.kill()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ I/O

    def _send(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise McpProtocolError("transport not started")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpProtocolError(f"send failed: {exc}") from exc

    def _read_line(self) -> str:
        """Lee una línea acotada por ``self._timeout`` (ADR-035 dec.: el
        budget por request se aplica de verdad). Lee a nivel de fd con
        ``os.read`` + ``select`` para que un server colgado no bloquee el
        loop agéntico indefinidamente. El deadline es por línea de respuesta.
        """
        if self._proc is None or self._proc.stdout is None:
            raise McpProtocolError("transport not started")
        fd = self._proc.stdout.fileno()
        deadline = time.monotonic() + self._timeout
        while "\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpProtocolError(
                    f"server response timed out after {self._timeout}s"
                )
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError as exc:
                raise McpProtocolError(f"read failed: {exc}") from exc
            if not chunk:
                # EOF — server murió. Recogemos stderr para diagnóstico.
                stderr = ""
                try:
                    if self._proc.stderr is not None:
                        stderr = self._proc.stderr.read() or ""
                except Exception:  # noqa: BLE001
                    pass
                raise McpProtocolError(
                    f"server closed stdout (rc={self._proc.poll()}). stderr: {stderr[:500]}"
                )
            self._buf += chunk.decode("utf-8", errors="replace")
        line, self._buf = self._buf.split("\n", 1)
        return line

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            if self._proc is None:
                self.start()
            req_id = self._next_id
            self._next_id += 1
            payload: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
            }
            if params is not None:
                payload["params"] = params
            self._send(payload)
            # Lee respuestas hasta encontrar la del req_id (los servers MCP
            # pueden emitir notificaciones intercaladas; las descartamos).
            for _ in range(64):
                line = self._read_line()
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise McpProtocolError(f"non-JSON line: {line[:200]}") from exc
                if not isinstance(msg, dict):
                    continue
                if msg.get("id") != req_id:
                    continue  # notificación o respuesta antigua
                if "error" in msg:
                    err = msg["error"] or {}
                    raise McpProtocolError(
                        f"server error {err.get('code')}: {err.get('message', '')}"
                    )
                return msg.get("result")
            raise McpProtocolError("too many out-of-band messages before response")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        with self._lock:
            if self._proc is None:
                self.start()
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                payload["params"] = params
            self._send(payload)
