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
from collections import Counter
from typing import Any, Callable

from pathlib import Path

from atlas.mcp.config import (
    McpServerConfig,
    is_valid_mcp_identifier,
    save_servers,
)
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
        merkle_log: Callable[..., Any] | None = None,
        sentinel: SentinelGate | None = None,
        persist_path: Path | str | None = None,
    ) -> None:
        counts = Counter(cfg.name for cfg in configs)
        self._invalid_configs: dict[str, str] = {}
        for cfg in configs:
            if not is_valid_mcp_identifier(cfg.name):
                self._invalid_configs[cfg.name] = (
                    "identificador vacío, ambiguo o fuera del alfabeto permitido"
                )
            elif counts[cfg.name] > 1:
                self._invalid_configs[cfg.name] = "nombre de server duplicado"
        self._configs = [
            cfg for cfg in configs if cfg.name not in self._invalid_configs
        ]
        self._transports: dict[str, McpTransport] = {}
        self._tool_specs: list[dict[str, Any]] = []
        self._read_only: set[str] = set()
        self._tool_index: dict[str, tuple[str, str]] = {}  # full → (server, tool)
        # Un drift detectado durante re-vetting revoca el server durante toda
        # la vida del proceso. Borrar/reaprobar el snapshot requiere reiniciar:
        # no se permite que el spawn perezoso deshaga una cuarentena.
        self._sentinel_quarantine: set[str] = set()
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
        for name, reason in self._invalid_configs.items():
            self._audit("mcp.server_vetoed", name, reason, "blocked")
        for cfg in self._configs:
            if not cfg.enabled:
                continue
            try:
                self._start_one(cfg)
            except Exception as exc:  # noqa: BLE001
                _log.warning("MCP server '%s' failed to start: %s", cfg.name, exc)
                self._audit("mcp.server_failed", cfg.name, str(exc)[:300], "failure")

    def _start_one(self, cfg: McpServerConfig) -> None:
        if cfg.name in self._sentinel_quarantine:
            self._audit(
                "sentinel.server_quarantined",
                cfg.name,
                "reinicio bloqueado hasta re-aprobación y nuevo proceso",
                "blocked",
            )
            return
        # Gate Atlas Sentinel (ADR-038), capa 2 pre-spawn: si el comando es
        # peligroso NO se arranca el subproceso (vetar después de spawn sería
        # tarde — el proceso ya habría corrido).
        if self._sentinel is not None:
            cmd_reason = self._sentinel.vet_command(cfg)
            if cmd_reason is not None:
                self._audit("mcp.server_vetoed", cfg.name, cmd_reason[:300], "failure")
                return
        # Fail-fast pre-spawn si faltan secretos declarados (2026-07-10): sin
        # esto, un server con env_passthrough sin configurar se spawnea, muere
        # con stacktrace y se reintenta en cada pasada — 530 apariciones de
        # ai.agenttrust en .atlas.err por no tener AGENTTRUST_API_KEY.
        _env, missing = cfg.resolve_env()
        if missing:
            self._audit(
                "mcp.server_skipped_missing_env", cfg.name,
                f"secretos ausentes: {','.join(missing)}", "failure",
            )
            return
        if not self._audit_before_effect(
            "mcp.server_start_requested",
            cfg.name,
            "comando admitido; creación de transporte pendiente",
        ):
            return
        transport: McpTransport | None = None
        committed = False
        try:
            transport = self._factory(cfg)
            # initialize handshake
            result = transport.request("initialize", {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            })
            transport.notify("notifications/initialized", {})
            tools = self._validated_tools(
                transport.request("tools/list", {}), cfg.name
            )

            # Gate Atlas Sentinel (ADR-038), capas 1+3 post-list: vetar las
            # tools antes de registrar transporte o índices.
            admitted_tools = {str(t["name"]) for t in tools}
            tiers: dict[str, str] = {}
            if self._sentinel is not None:
                try:
                    vet = self._sentinel.vet_tools(cfg, tools)
                except Exception as exc:  # noqa: BLE001
                    self._sentinel_quarantine.add(cfg.name)
                    self._audit(
                        "sentinel.server_vetoed",
                        cfg.name,
                        f"fallo interno durante vetting: {exc}",
                        "blocked",
                    )
                    raise
                if not vet.admitted:
                    self._sentinel_quarantine.add(cfg.name)
                    self._audit(
                        "sentinel.server_vetoed",
                        cfg.name,
                        vet.server_reason,
                        "blocked",
                    )
                    return
                admitted_tools = {
                    verdict.tool_name for verdict in vet.tools if verdict.admitted
                }
                tiers = {
                    verdict.tool_name: verdict.tier
                    for verdict in vet.tools
                    if verdict.admitted
                }
                if not admitted_tools:
                    self._sentinel_quarantine.add(cfg.name)
                    self._audit(
                        "sentinel.server_vetoed",
                        cfg.name,
                        "ninguna tool superó el vetting",
                        "blocked",
                    )
                    return

            read_only = set(cfg.read_only_tools)
            new_specs: list[dict[str, Any]] = []
            new_index: dict[str, tuple[str, str]] = {}
            new_read_only: set[str] = set()
            for tool in tools:
                tool_name = str(tool["name"])
                if tool_name not in admitted_tools:
                    continue
                full = f"mcp__{cfg.name}__{tool_name}"
                new_index[full] = (cfg.name, tool_name)
                if (
                    tool_name in read_only
                    and (self._sentinel is None or tiers.get(tool_name) == "read")
                ):
                    new_read_only.add(full)
                new_specs.append({
                    "type": "function",
                    "function": {
                        "name": full,
                        "description": str(tool.get("description") or "")[:1024],
                        "parameters": tool.get("inputSchema") or {
                            "type": "object",
                            "properties": {},
                        },
                    },
                })

            # Commit único: ningún estado parcial es visible antes de aquí.
            self._transports[cfg.name] = transport
            self._tool_index.update(new_index)
            self._read_only.update(new_read_only)
            self._tool_specs.extend(new_specs)
            committed = True
            self._audit(
                "mcp.server_started",
                cfg.name,
                (
                    f"tools_advertised={len(tools)} "
                    f"tools_admitted={len(new_specs)} "
                    f"protocol={result.get('protocolVersion') if isinstance(result, dict) else '?'}"
                ),
                "success",
            )
        finally:
            if transport is not None and not committed:
                try:
                    transport.close()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _validated_tools(response: Any, server: str) -> list[dict[str, Any]]:
        if not isinstance(response, dict) or not isinstance(
            response.get("tools"), list
        ):
            raise McpProtocolError(
                f"server '{server}': tools/list debe devolver una lista"
            )
        tools = response["tools"]
        if not tools:
            raise McpProtocolError(
                f"server '{server}': tools/list vacío no es analizable"
            )
        names: list[str] = []
        clean: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                raise McpProtocolError(
                    f"server '{server}': definición de tool no es un objeto"
                )
            name = tool.get("name")
            schema = tool.get("inputSchema", {})
            if not isinstance(name, str) or not is_valid_mcp_identifier(name):
                raise McpProtocolError(
                    f"server '{server}': nombre de tool inválido o ambiguo"
                )
            if not isinstance(schema, dict):
                raise McpProtocolError(
                    f"server '{server}': inputSchema de '{name}' no es objeto"
                )
            names.append(name)
            clean.append(tool)
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise McpProtocolError(
                f"server '{server}': nombres de tool duplicados {duplicates}"
            )
        return clean

    def ensure_started(self, server_name: str) -> bool:
        """Arranca ``server_name`` en diferido si aún no está activo.

        Idempotente: si ya está en ``_transports``, no hace nada. Devuelve
        ``True`` si el server quedó disponible (en ``_transports``). Los fallos
        se loggean pero no se elevan — igual que ``start_all``."""
        if server_name in self._transports:
            return True
        if server_name in self._sentinel_quarantine:
            return False
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
        if not is_valid_mcp_identifier(cfg.name):
            return f"vetoed: server '{cfg.name}' tiene identificador inválido"
        existing = next((item for item in self._configs if item.name == cfg.name), None)
        if existing is not None and existing != cfg:
            return (
                f"vetoed: server '{cfg.name}' contradice la configuración "
                "existente"
            )
        if cfg.name in self._transports:
            return f"skipped: server '{cfg.name}' ya está activo"
        if cfg.name in self._sentinel_quarantine:
            return (
                f"vetoed: server '{cfg.name}' en cuarentena Sentinel; "
                "requiere re-aprobación y reinicio"
            )
        if not cfg.enabled:
            return f"skipped: server '{cfg.name}' deshabilitado"
        # Backoff persistente de adopción (2026-07-10): el lazo de adopción
        # re-proponía el mismo candidato roto en CADA pasada — ai.agenttrust
        # (muere al arrancar sin AGENTTRUST_API_KEY) acumuló 530 stacktraces
        # en .atlas.err. Mismo patrón que la cola de self-build: N fallos de
        # arranque seguidos → skip auditado hasta intervención manual (borrar
        # la entrada del sidecar o configurar el secreto).
        failures = self._load_start_failures()
        if failures.get(cfg.name, 0) >= self._MAX_START_FAILURES:
            return (
                f"skipped: server '{cfg.name}' con "
                f"{failures[cfg.name]} fallos de arranque previos (backoff persistente)"
            )
        try:
            self._start_one(cfg)
        except Exception as exc:  # noqa: BLE001
            _log.warning("MCP server '%s' failed to start: %s", cfg.name, exc)
            self._audit("mcp.server_failed", cfg.name, str(exc)[:300], "failure")
            self._record_start_failure(cfg.name)
            return f"error: {exc}"
        self._clear_start_failure(cfg.name)
        if cfg.name not in self._transports:
            # _start_one volvió sin registrar ⇒ el gate lo vetó.
            return f"vetoed: server '{cfg.name}' rechazado por el gate de adopción"
        if cfg.name not in {c.name for c in self._configs}:
            self._configs.append(cfg)
        self._persist()
        return f"ok: server '{cfg.name}' adoptado"

    def remove_server(self, name: str) -> bool:
        """Retira un server en caliente: cierra su transporte y descarta sus
        tools/config/cuarentena. También funciona después de una revocación."""
        had_config = any(cfg.name == name for cfg in self._configs)
        was_quarantined = name in self._sentinel_quarantine
        transport = self._transports.pop(name, None)
        if transport is not None:
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
        self._sentinel_quarantine.discard(name)
        self._persist()
        self._audit("mcp.server_removed", name, f"tools={len(fulls)}", "success")
        return transport is not None or had_config or was_quarantined

    _MAX_START_FAILURES = 3

    def _failures_path(self) -> "Path | None":
        if self._persist_path is None:
            return None
        return self._persist_path.with_name(self._persist_path.stem + "_start_failures.json")

    def _load_start_failures(self) -> dict[str, int]:
        path = self._failures_path()
        if path is None or not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _record_start_failure(self, name: str) -> None:
        path = self._failures_path()
        if path is None:
            return
        failures = self._load_start_failures()
        failures[name] = failures.get(name, 0) + 1
        try:
            path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _clear_start_failure(self, name: str) -> None:
        path = self._failures_path()
        if path is None:
            return
        failures = self._load_start_failures()
        if name in failures:
            failures.pop(name)
            try:
                path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
            except OSError:
                pass

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
        """Solo afirma read tras arrancar, validar y vetar la superficie real."""
        parts = full_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return False
        server, _tool = parts[1], parts[2]
        if not self.ensure_started(server):
            return False
        return full_name in self._read_only

    def knows(self, full_name: str) -> bool:
        return full_name in self._tool_index

    def revet_all(self) -> list[dict[str, Any]]:
        """Capa 6 (re-vetting periódico, ADR-038): re-corre
        ``SentinelGate.vet_tools`` sobre cada server YA adoptado y corriendo,
        contra su snapshot guardado -- detecta drift ocurrido FUERA de una
        adopción nueva (p.ej. un server que reescribió su propio binario
        in-place). El escaneo no reescribe snapshots; un fallo o drift revoca
        el transporte y sus tools y lo deja en cuarentena hasta re-aprobación
        HITL + reinicio. Re-minado de claude-mcp-sentinel v3.1 ("scheduled
        monitoring, re-escanea todo cada mañana")."""
        if self._sentinel is None:
            return []
        findings: list[dict[str, Any]] = []
        for cfg in self._configs:
            transport = self._transports.get(cfg.name)
            if transport is None:
                continue
            try:
                clean = self._validated_tools(
                    transport.request("tools/list", {}), cfg.name
                )
                vet = self._sentinel.vet_tools(cfg, clean)
            except Exception as exc:  # noqa: BLE001 — protección degradada
                self._quarantine_server(
                    cfg.name, f"re-vetting falló: {exc}"
                )
                findings.append(
                    {
                        "server": cfg.name,
                        "error": str(exc)[:300],
                        "revoked": True,
                        "pending_review": True,
                    }
                )
                continue
            blocked = [
                {"tool": v.tool_name, "reason": v.reason} for v in vet.tools if not v.admitted
            ]
            if not vet.admitted and not blocked:
                blocked.append({"tool": "<server>", "reason": vet.server_reason})
            if blocked or not vet.admitted:
                self._quarantine_server(
                    cfg.name, f"{len(blocked)} hallazgo(s) de Sentinel"
                )
                findings.append(
                    {
                        "server": cfg.name,
                        "blocked": blocked,
                        "revoked": True,
                        "pending_review": True,
                    }
                )
                self._audit(
                    "sentinel.revet_drift", cfg.name,
                    f"{len(blocked)} hallazgo(s); server revocado", "blocked",
                )
        return findings

    def _quarantine_server(self, name: str, reason: str) -> None:
        """Revoca runtime sin borrar la configuración ni rearmar TOFU."""
        transport = self._transports.pop(name, None)
        if transport is not None:
            try:
                transport.close()
            except Exception:  # noqa: BLE001
                pass
        fulls = {f for f, (srv, _tool) in self._tool_index.items() if srv == name}
        for full in fulls:
            self._tool_index.pop(full, None)
            self._read_only.discard(full)
        self._tool_specs = [
            spec
            for spec in self._tool_specs
            if spec.get("function", {}).get("name") not in fulls
        ]
        self._sentinel_quarantine.add(name)
        self._audit(
            "sentinel.server_revoked",
            name,
            f"{reason}; tools={len(fulls)}",
            "blocked",
        )

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

        if self._sentinel is not None:
            veto_reason = self._sentinel.vet_call(tool, args)
            if veto_reason is not None:
                self._audit("sentinel.call_vetoed", full_name, veto_reason, "blocked")
                return f"error: MCP {full_name}: bloqueado por Sentinel — {veto_reason}"

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
                risk_level="moderate" if outcome in {"failure", "blocked"} else "safe",
                payload={"server": server, "detail": detail[:500]},
            )
        except Exception:  # noqa: BLE001
            pass

    def _audit_before_effect(self, action: str, server: str, detail: str) -> bool:
        """Registra un efecto pendiente; un logger configurado que falla veta.

        La ausencia explícita de logger se mantiene para arneses aislados. En
        runtime gobernado, donde se inyecta Merkle, degradar la evidencia no
        concede permiso para crear el transporte externo.
        """
        if self._merkle_log is None:
            return True
        try:
            self._merkle_log(
                action=action,
                agent="orchestrator.mcp",
                result="requested",
                risk_level="moderate",
                payload={"server": server, "detail": detail[:500]},
            )
        except Exception:  # noqa: BLE001 — límite de auditoría fail-closed
            _log.error(
                "MCP server '%s' not started: pre-effect audit failed",
                server,
                exc_info=True,
            )
            return False
        return True
