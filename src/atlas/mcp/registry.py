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

from atlas.mcp.config import McpServerConfig
from atlas.mcp.transport import McpProtocolError, McpTransport, StdioTransport
from atlas.security.sentinel_gate import SentinelGate

_log = logging.getLogger(__name__)

# Protocol version mínimo soportado. Los servers MCP actuales declaran
# "2024-11-05" o "2025-06-18"; aceptamos lo que pidan (intencionalmente laxo
# hasta que aparezcan diferencias de protocolo relevantes).
_CLIENT_INFO = {"name": "atlas-core", "version": "0.12.0"}
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
    ) -> None:
        self._configs = list(configs)
        self._transports: dict[str, McpTransport] = {}
        self._tool_specs: list[dict[str, Any]] = []
        self._read_only: set[str] = set()
        self._tool_index: dict[str, tuple[str, str]] = {}  # full → (server, tool)
        self._merkle_log = merkle_log
        self._sentinel = sentinel
        self._factory = transport_factory or self._default_factory

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

        # Gate de adopción Atlas Sentinel (ADR-038): vetar server + tools antes
        # de registrarlas. Fail-closed: lo que no pasa, no se adopta.
        admitted_tools: set[str] | None = None
        if self._sentinel is not None:
            clean = [t for t in tools if isinstance(t, dict)]
            vet = self._sentinel.vet(cfg, clean)
            if not vet.admitted:
                try:
                    transport.close()
                except Exception:  # noqa: BLE001
                    pass
                self._audit(
                    "mcp.server_vetoed", cfg.name, vet.server_reason[:300], "failure",
                )
                return
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
