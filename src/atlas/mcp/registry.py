"""Registry de servers MCP — ADR-035.

Orquesta: spawn de transportes, handshake ``initialize``, ``tools/list``,
namespacing ``mcp__<server>__<tool>``, dispatch a ``tools/call`` y
mantenimiento del set de tools mutantes (todas por defecto; el config
marca las de lectura).

Auditoría: cada call se loggea en Merkle con tool + ok/fail. Los
``arguments`` se guardan en raw — si el server los contamina con secretos,
es responsabilidad del config (env_passthrough) no enviárselos en primer
lugar. Los resultados se truncan antes de loggear para evitar
contaminar el Merkle con outputs grandes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from pathlib import Path

from atlas.mcp.config import McpServerConfig, save_servers
from atlas.mcp.transport import McpProtocolError, McpTransport, StdioTransport
from atlas.security.sentinel_gate import SentinelGate
from atlas import __version__

_log = logging.getLogger(__name__)

# Protocol version mínimo soportado. Los servers MCP actuales declaran
# "2024-11-05" o "2025-06-18"; aceptamos lo que pidan (intencionalmente laxo
# hasta que aparezcan diferencias de protocolo relevantes).
_CLIENT_INFO = {"name": "atlas-core", "version": __version__}
_PROTOCOL_VERSION = "2025-06-18"


class McpRegistry:
    """Posee los transportes a servers MCP y expone sus tools al loop."""

    def __init__(
        self,
        configs: list[McpServerConfig],
        *,
        transport_factory: Callable[[McpServerConfig], McpTransport] | None = None,
        merkle_log: Callable[..., None] | None = None,
        sentinel: SentinelGate | None = None,
        persist_path: Path | str | None = None,
    ) -> None:
        self._configs = list(configs)
        self._transports: dict[str, McpTransport] = {}
        self._tool_specs: list[dict[str, Any]] = []
        self._read_only: set[str] = set()
        self._tool_index: dict[str, tuple[str, str]] = {}  # full → (server, tool)
        self._merkle_log = merkle_log
        self._sentinel = sentinel
        self._factory = transport_factory or self._default_factory
        # 2026-07-04: add_server()/remove_server() solo mutaban self._configs
        # EN MEMORIA — una adopción "ok:" nunca sobrevivía a un reinicio
        # (load_servers() vuelve a leer este mismo fichero al arrancar y no
        # veía nada nuevo). persist_path cierra ese hueco: cada mutación
        # exitosa reescribe el fichero real, así una adopción aprobada por el
        # decisor (o un undo) persiste de verdad.
        self._persist_path = Path(persist_path) if persist_path else None

    @staticmethod
    def _default_factory(cfg: McpServerConfig) -> McpTransport:
        env, missing = cfg.resolve_env()
        if missing:
            raise McpProtocolError(
                f"server '{cfg.name}': missing env vars {missing}"
            )
        return StdioTransport(
            cmd=cfg.cmd,
            env=env,
            cwd=cfg.cwd,
            timeout_seconds=cfg.timeout_seconds,
        )

    # ------------------------------------------------------------------ lifecycle

    def start_all(self) -> None:
        """Arranca todos los servers habilitados; servers que fallen quedan
        fuera (no rompen el resto). El error se loggea, no se eleva."""
        for cfg in self._configs:
            if not cfg.enabled:
                continue
            try:
                self._start_one(cfg)
            except Exception as exc:  # noqa: BLE001
                _log.warning("MCP server '%s' failed to start: %s", cfg.name, exc)
                self._audit("mcp.server_failed", cfg.name, str(exc)[:300], "failure")

    def _start_one(self, cfg: McpServerConfig) -> None:
        # Gate Atlas Sentinel (ADR-038), capa 2 pre-spawn: si el comando es
        # peligroso NO se arranca el subproceso (vetar después de spawn sería
        # tarde — el proceso ya habría corrido).
        if self._sentinel is not None:
            cmd_reason = self._sentinel.vet_command(cfg)
            if cmd_reason is not None:
                self._audit("mcp.server_vetoed", cfg.name, cmd_reason[:300], "failure")
                return
        transport = self._factory(cfg)
        # initialize handshake
        result = transport.request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        })
        transport.notify("notifications/initialized", {})
        # tools/list
        tools_resp = transport.request("tools/list", {})
        tools = (tools_resp or {}).get("tools", []) if isinstance(tools_resp, dict) else []

        # Gate Atlas Sentinel (ADR-038), capas 1+3 post-list: vetar las tools
        # antes de registrarlas. Fail-closed: lo que no pasa, no se adopta.
        admitted_tools: set[str] | None = None
        if self._sentinel is not None:
            clean = [t for t in tools if isinstance(t, dict)]
            vet = self._sentinel.vet_tools(cfg, clean)
            admitted_tools = {v.tool_name for v in vet.tools if v.admitted}

        self._transports[cfg.name] = transport
        read_only = set(cfg.read_only_tools)
        for t in tools:
            if not isinstance(t, dict):
                continue
            tool_name = str(t.get("name") or "")
            if not tool_name:
                continue
            if admitted_tools is not None and tool_name not in admitted_tools:
                continue
            full = f"mcp__{cfg.name}__{tool_name}"
            self._tool_index[full] = (cfg.name, tool_name)
            if tool_name in read_only:
                self._read_only.add(full)
            self._tool_specs.append({
                "type": "function",
                "function": {
                    "name": full,
                    "description": str(t.get("description") or "")[:1024],
                    "parameters": t.get("inputSchema") or {
                        "type": "object",
                        "properties": {},
                    },
                },
            })
        self._audit(
            "mcp.server_started", cfg.name,
            f"tools={len(tools)} protocol={result.get('protocolVersion') if isinstance(result, dict) else '?'}",
            "success",
        )

    def ensure_started(self, server_name: str) -> bool:
        """Arranca ``server_name`` en diferido si aún no está activo.

        Idempotente: si ya está en ``_transports``, no hace nada. Devuelve
        ``True`` si el server quedó disponible (en ``_transports``). Los fallos
        se loggean pero no se elevan — igual que ``start_all``."""
        if server_name in self._transports:
            return True
        cfg = next((c for c in self._configs if c.name == server_name and c.enabled), None)
        if cfg is None:
            return False
        try:
            self._start_one(cfg)
        except Exception as exc:  # noqa: BLE001
            _log.warning("MCP server '%s' failed to start (lazy): %s", server_name, exc)
            self._audit("mcp.server_failed", server_name, str(exc)[:300], "failure")
        return server_name in self._transports

    def close_all(self) -> None:
        for transport in self._transports.values():
            try:
                transport.close()
            except Exception:  # noqa: BLE001
                pass
        self._transports.clear()
        self._tool_specs.clear()
        self._read_only.clear()
        self._tool_index.clear()

    # ------------------------------------------------------------------ dynamic

    def add_server(self, cfg: McpServerConfig) -> str:
        """Adopta un server en caliente, sin reiniciar el resto. Pasa por el
        mismo gate Sentinel que ``start_all``. Devuelve un estado textual
        (``ok`` / ``skipped`` / ``vetoed`` / ``error``) para que el llamante
        (Telegram, auto-mantenimiento) lo reporte. Fail-safe: un fallo no
        afecta a los servers ya activos."""
        if cfg.name in self._transports:
            return f"skipped: server '{cfg.name}' ya está activo"
        if not cfg.enabled:
            return f"skipped: server '{cfg.name}' deshabilitado"
        try:
            self._start_one(cfg)
        except Exception as exc:  # noqa: BLE001
            _log.warning("MCP server '%s' failed to start: %s", cfg.name, exc)
            self._audit("mcp.server_failed", cfg.name, str(exc)[:300], "failure")
            return f"error: {exc}"
        if cfg.name not in self._transports:
            # _start_one volvió sin registrar ⇒ el gate lo vetó.
            return f"vetoed: server '{cfg.name}' rechazado por el gate de adopción"
        if cfg.name not in {c.name for c in self._configs}:
            self._configs.append(cfg)
        self._persist()
        return f"ok: server '{cfg.name}' adoptado"

    def remove_server(self, name: str) -> bool:
        """Retira un server en caliente: cierra su transporte y descarta sus
        tools del surface. Devuelve False si no estaba activo."""
        transport = self._transports.pop(name, None)
        if transport is None:
            return False
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass
        fulls = {f for f, (srv, _t) in self._tool_index.items() if srv == name}
        for full in fulls:
            self._tool_index.pop(full, None)
            self._read_only.discard(full)
        self._tool_specs = [
            s for s in self._tool_specs
            if s.get("function", {}).get("name") not in fulls
        ]
        self._configs = [c for c in self._configs if c.name != name]
        self._persist()
        self._audit("mcp.server_removed", name, f"tools={len(fulls)}", "success")
        return True

    def _persist(self) -> None:
        """Reescribe ``persist_path`` con el estado actual de ``_configs``.
        Best-effort: un fallo de disco no debe tumbar una adopción/retirada
        ya aplicada en caliente — solo se pierde la durabilidad, no el
        efecto inmediato de esta sesión."""
        if self._persist_path is None:
            return
        try:
            save_servers(self._persist_path, self._configs)
        except OSError as exc:
            _log.warning("no se pudo persistir mcp_servers en %s: %s", self._persist_path, exc)

    # ------------------------------------------------------------------ surface

    def tool_specs(self) -> list[dict[str, Any]]:
        """Specs en formato OpenAI/LiteLLM para alimentar el loop agéntico."""
        return list(self._tool_specs)

    def is_read_only(self, full_name: str) -> bool:
        """ADR-035 dec.5: por defecto mutate (HITL). Solo los que el config
        marca explícitamente son lectura."""
        return full_name in self._read_only

    def knows(self, full_name: str) -> bool:
        return full_name in self._tool_index

    def dispatch(self, full_name: str, arguments: str | dict[str, Any]) -> str:
        """Llama ``tools/call`` en el server correcto y devuelve el resultado
        como texto. Errores se devuelven como texto (consistente con el
        contrato del loop: el modelo debe poder reaccionar)."""
        # Spawn perezoso: si el nombre tiene el prefijo mcp__ intentamos arrancar
        # el server dueño antes de consultar el índice.
        if full_name.startswith("mcp__"):
            server_hint = full_name.split("__")[1]
            self.ensure_started(server_hint)

        if full_name not in self._tool_index:
            return f"error: tool MCP desconocida '{full_name}'"
        server, tool = self._tool_index[full_name]
        transport = self._transports.get(server)
        if transport is None:
            return f"error: server MCP '{server}' no disponible"

        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = arguments
        if not isinstance(args, dict):
            args = {}

        try:
            result = transport.request("tools/call", {
                "name": tool,
                "arguments": args,
            })
        except McpProtocolError as exc:
            self._audit("mcp.tool_failed", full_name, str(exc)[:300], "failure")
            return f"error: MCP {full_name}: {exc}"

        text = self._stringify(result)
        self._audit("mcp.tool_called", full_name, f"chars={len(text)}", "success")
        return text

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _stringify(result: Any) -> str:
        """Convierte la respuesta MCP a texto. El formato canónico es
        ``{content: [{type: 'text', text: '...'}, ...], isError?: bool}``;
        toleramos variantes y caemos a JSON si no encaja."""
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                if parts:
                    text = "\n".join(parts)
                    if result.get("isError"):
                        return f"error: {text}"
                    return text
            return json.dumps(result, ensure_ascii=False, default=str)[:4000]
        return str(result)

    def _audit(self, action: str, server: str, detail: str, outcome: str) -> None:
        if self._merkle_log is None:
            return
        try:
            self._merkle_log(
                action=action,
                agent="orchestrator.mcp",
                result=outcome,
                risk_level="moderate" if outcome == "failure" else "safe",
                payload={"server": server, "detail": detail[:500]},
            )
        except Exception:  # noqa: BLE001
            pass
