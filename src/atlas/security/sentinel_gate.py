"""Gate de adopción "Atlas Sentinel" — ADR-038 (muralla P0 de adopción).

Internaliza la tesis de ``claude-mcp-sentinel`` ("skills y MCP no son confiables
por defecto") como primitiva nativa de Atlas. **No instalamos su código** (sería,
irónicamente, otra decisión de cadena de suministro); robamos el concepto y lo
construimos **fail-closed para adopción**: si un server/tool no se puede vetar, no
se adopta.

Punto de enganche: ``McpRegistry._start_one`` (ADR-035), tras ``tools/list`` y
antes de registrar las tools en el loop. Cada veredicto se audita en Merkle.

Capas implementadas en este slice (las demás quedan documentadas en el ADR como
diferidas):

1. **Identidad criptográfica + snapshot (anti rug-pull).** ``sha256`` del tool
   definition (name+description+inputSchema). Primera adopción = TOFU (trust on
   first use): se admite y se graba el snapshot. En adopciones posteriores, un
   hash distinto (drift) o una tool nueva en un server ya conocido se **bloquean**
   hasta re-aprobación humana (borrar el snapshot del server).
2. **IOC / coherencia de comando.** El ``cmd`` del server es argv (nunca shell,
   ADR-035): si un token trae metacaracteres de shell es un intento de smuggling
   y se veta el server entero. Dominios/comandos en una blocklist inyectable
   bloquean tool o server.
3. **Tiering + bloqueo de credenciales.** Cada tool se clasifica en read / write /
   shell_net / credential. Las de tier ``credential`` no se adoptan (fail-closed):
   una tool que dice manejar secretos no entra sin decisión humana explícita.

Diferido (ver ADR-038): coherencia AST profunda (reusar ``ast_guard``), egress
IOC runtime en cada ``tools/call``, y re-vetting atado a ColdUpdate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atlas.mcp.config import McpServerConfig

# Metacaracteres de shell que NUNCA deben aparecer en un token argv legítimo.
# Su presencia indica un intento de smuggling de shell en el comando del server.
_SHELL_METACHARS: tuple[str, ...] = (
    ";", "|", "$(", "`", "&&", "||", ">", "<", "\n",
)

# Keywords de tiering. Orden de precedencia: credential > shell_net > write > read.
_CREDENTIAL_KW: tuple[str, ...] = (
    "credential", "password", "passwd", "secret", "token", "api_key", "apikey",
    "api key", "private key", "ssh key", "keychain", "vault", "env var",
    "environment variable", "access key",
)
_SHELL_NET_KW: tuple[str, ...] = (
    "shell", "exec", "command", "bash", "subprocess", "http", "fetch",
    "request", "url", "download", "upload", "network", "socket", "curl",
)
_WRITE_KW: tuple[str, ...] = (
    "write", "create", "update", "delete", "modify", "insert", "remove",
    "edit", "send", "post", "put", "patch", "publish", "deploy", "move",
)


@dataclass(frozen=True)
class ToolVerdict:
    """Veredicto por tool descubierta."""

    tool_name: str
    tier: str  # read | write | shell_net | credential
    admitted: bool
    reason: str


@dataclass(frozen=True)
class VetResult:
    """Resultado del vetting de un server y su superficie de tools."""

    server: str
    admitted: bool          # decisión a nivel server (False ⇒ no se adopta nada)
    server_reason: str
    tools: list[ToolVerdict] = field(default_factory=list)


class SentinelGate:
    """Vetador fail-closed de servers MCP en el momento de adopción."""

    def __init__(
        self,
        snapshot_dir: Path,
        *,
        merkle_log: Callable[..., Any] | None = None,
        ioc_domains: frozenset[str] = frozenset(),
        ioc_commands: frozenset[str] = frozenset(),
    ) -> None:
        self._snapshot_dir = Path(snapshot_dir)
        self._merkle_log = merkle_log
        self._ioc_domains = frozenset(d.lower() for d in ioc_domains)
        self._ioc_commands = frozenset(c.lower() for c in ioc_commands)

    # ------------------------------------------------------------------ API

    def vet(self, cfg: McpServerConfig, tools: list[dict[str, Any]]) -> VetResult:
        """Veta un server y sus tools. Fail-closed: lo que no se puede vetar
        no se admite. No arranca nada — solo decide."""
        # Capa 2 (server-level): el cmd es argv; metacaracteres de shell o un
        # comando en la IOC blocklist vetan el server entero.
        cmd_reason = self._scan_command(cfg.cmd)
        if cmd_reason is not None:
            self._audit("sentinel.server_vetoed", cfg.name, cmd_reason, "blocked")
            return VetResult(server=cfg.name, admitted=False, server_reason=cmd_reason)

        snapshot = self._load_snapshot(cfg.name)
        first_adoption = snapshot is None
        known = snapshot or {}

        verdicts: list[ToolVerdict] = []
        new_snapshot: dict[str, str] = {}
        for t in tools:
            name = str(t.get("name") or "")
            if not name:
                continue
            verdict = self._vet_tool(name, t, known, first_adoption)
            verdicts.append(verdict)
            if verdict.admitted:
                new_snapshot[name] = self._tool_hash(t)

        # En primera adopción (TOFU) grabamos el snapshot de lo admitido para que
        # las próximas adopciones detecten drift/rug-pull.
        if first_adoption and new_snapshot:
            self._save_snapshot(cfg.name, new_snapshot)
            self._audit(
                "sentinel.first_adoption", cfg.name,
                f"tools_admitted={len(new_snapshot)}", "success",
            )

        return VetResult(
            server=cfg.name,
            admitted=True,
            server_reason="ok",
            tools=verdicts,
        )

    # ------------------------------------------------------------------ tool

    def _vet_tool(
        self,
        name: str,
        tool: dict[str, Any],
        known: dict[str, str],
        first_adoption: bool,
    ) -> ToolVerdict:
        surface = self._tool_surface(tool)

        # Capa 2 (tool-level): IOC en descripción/schema.
        ioc = self._scan_iocs(surface)
        if ioc is not None:
            self._audit("sentinel.tool_vetoed", name, ioc, "blocked")
            return ToolVerdict(name, tier="unknown", admitted=False, reason=ioc)

        # Capa 3: tiering. Las de credenciales no se adoptan.
        tier = self._classify_tier(name, surface)
        if tier == "credential":
            reason = "tier=credential: tool maneja secretos, requiere HITL explícito"
            self._audit("sentinel.tool_vetoed", name, reason, "blocked")
            return ToolVerdict(name, tier=tier, admitted=False, reason=reason)

        # Capa 1: identidad/snapshot (anti rug-pull) en adopciones posteriores.
        if not first_adoption:
            current = self._tool_hash(tool)
            if name not in known:
                reason = "tool nueva en server conocido (posible rug-pull); bloqueada"
                self._audit("sentinel.drift_blocked", name, reason, "blocked")
                return ToolVerdict(name, tier=tier, admitted=False, reason=reason)
            if known[name] != current:
                reason = "hash de la tool cambió desde la adopción (drift); bloqueada"
                self._audit("sentinel.drift_blocked", name, reason, "blocked")
                return ToolVerdict(name, tier=tier, admitted=False, reason=reason)

        return ToolVerdict(name, tier=tier, admitted=True, reason="ok")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _tool_hash(tool: dict[str, Any]) -> str:
        canonical = json.dumps(
            {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "inputSchema": tool.get("inputSchema"),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _tool_surface(tool: dict[str, Any]) -> str:
        parts = [
            str(tool.get("name") or ""),
            str(tool.get("description") or ""),
            json.dumps(tool.get("inputSchema") or {}, ensure_ascii=False, default=str),
        ]
        return " ".join(parts).lower()

    def _scan_command(self, cmd: list[str]) -> str | None:
        for token in cmd:
            for meta in _SHELL_METACHARS:
                if meta in token:
                    return f"cmd token {token!r} contiene metacaracter de shell {meta!r}"
        joined = " ".join(cmd).lower()
        for bad in self._ioc_commands:
            if bad in joined:
                return f"cmd coincide con IOC '{bad}'"
        return None

    def _scan_iocs(self, surface: str) -> str | None:
        for dom in self._ioc_domains:
            if dom in surface:
                return f"superficie contiene dominio IOC '{dom}'"
        for bad in self._ioc_commands:
            if bad in surface:
                return f"superficie contiene comando IOC '{bad}'"
        return None

    @staticmethod
    def _classify_tier(name: str, surface: str) -> str:
        text = f"{name.lower()} {surface}"
        if any(kw in text for kw in _CREDENTIAL_KW):
            return "credential"
        if any(kw in text for kw in _SHELL_NET_KW):
            return "shell_net"
        if any(kw in text for kw in _WRITE_KW):
            return "write"
        return "read"

    # ------------------------------------------------------------------ snapshot

    def _snapshot_path(self, server: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in server)
        return self._snapshot_dir / f"{safe}.json"

    def _load_snapshot(self, server: str) -> dict[str, str] | None:
        path = self._snapshot_path(server)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items()}

    def _save_snapshot(self, server: str, snapshot: dict[str, str]) -> None:
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._snapshot_path(server)
        path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def _audit(self, action: str, server: str, detail: str, outcome: str) -> None:
        if self._merkle_log is None:
            return
        try:
            self._merkle_log(
                action=action,
                agent="security.sentinel",
                result=outcome,
                risk_level="moderate" if outcome == "blocked" else "safe",
                payload={"server": server, "detail": detail[:500]},
            )
        except Exception:  # noqa: BLE001
            pass
