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
4. **Coherencia description↔inputSchema.** ¿Lo que la tool AFIRMA que hace
   (``description``) coincide con lo que PIDE (``inputSchema``)? Ver la nota de
   investigación bajo ``_vet_coherence`` para la decisión ast_guard-sí/no.

Diferido (ver ADR-038): egress IOC runtime en cada ``tools/call``, y
re-vetting atado a ColdUpdate.
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

# Capa 4 — coherencia description↔inputSchema.
#
# Afirmaciones de "solo lectura" en la description que se pueden contrastar
# contra el inputSchema. Sin una afirmación así no hay nada verificable: una
# tool que se anuncia como de escritura/comando no dispara esta capa (no es
# incoherencia bloquear lo que ya se declara).
_READONLY_CLAIM_KW: tuple[str, ...] = (
    "solo lectura", "solo-lectura", "de lectura", "read-only", "read only",
    "readonly", "solo consulta", "no modifica", "no escribe", "no ejecuta",
    "sin efectos secundarios", "get-only", "únicamente lee", "unicamente lee",
    "no realiza cambios", "does not modify", "does not write",
)
# Nombres de parámetro en inputSchema que delatan ejecución de comando —
# señal FUERTE de incoherencia contra una description "solo lectura".
_COHERENCE_COMMAND_PARAM_KW: tuple[str, ...] = (
    "cmd", "command", "shell", "script", "bash", "exec", "subprocess",
)
# Señal FUERTE: parámetros de escritura/borrado en el schema.
_COHERENCE_WRITE_PARAM_KW: tuple[str, ...] = (
    "write", "overwrite", "delete", "content", "body", "payload",
)
# Señal DÉBIL: parámetro de URL/endpoint arbitrario. Una tool de lectura puede
# legítimamente pedir una URL a consultar (p.ej. "lee esta página") — no
# bloquea sola, solo se marca para revisión humana (evita falsos positivos).
_COHERENCE_URL_PARAM_KW: tuple[str, ...] = (
    "url", "endpoint", "webhook", "target_url", "uri",
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

    def vet_command(self, cfg: McpServerConfig) -> str | None:
        """Capa 2, **pre-spawn**: el ``cmd`` es argv (nunca shell, ADR-035).
        Metacaracteres de shell o un comando en la IOC blocklist vetan el server
        ANTES de arrancar el subproceso. Devuelve la razón del veto o None."""
        reason = self._scan_command(cfg.cmd)
        if reason is not None:
            self._audit("sentinel.server_vetoed", cfg.name, reason, "blocked")
        return reason

    def vet(self, cfg: McpServerConfig, tools: list[dict[str, Any]]) -> VetResult:
        """Conveniencia: comando + tools en una llamada (para callers que ya
        tienen la lista de tools). El registry usa ``vet_command`` pre-spawn y
        ``vet_tools`` post-list por separado."""
        cmd_reason = self.vet_command(cfg)
        if cmd_reason is not None:
            return VetResult(server=cfg.name, admitted=False, server_reason=cmd_reason)
        return self.vet_tools(cfg, tools)

    def vet_tools(self, cfg: McpServerConfig, tools: list[dict[str, Any]]) -> VetResult:
        """Capa 1+3, **post-list**: identidad/snapshot (anti rug-pull) y tiering.
        Asume que el comando ya pasó ``vet_command``. Fail-closed por tool."""
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

        # Capa 4: coherencia description↔inputSchema. Señal fuerte (comando o
        # escritura) bloquea aquí, antes de tiering; señal débil (URL) se
        # difiere para adjuntarse como "review" solo si la tool termina admitida.
        description = str(tool.get("description") or "")
        schema = tool.get("inputSchema")
        coherence_reason, strong = self._vet_coherence(
            description, schema if isinstance(schema, dict) else {}
        )
        if coherence_reason is not None and strong:
            self._audit("sentinel.tool_vetoed", name, coherence_reason, "blocked")
            return ToolVerdict(name, tier="unknown", admitted=False, reason=coherence_reason)

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

        if coherence_reason is not None:
            # Señal débil que sobrevivió a las demás capas: se admite (evita
            # falso positivo) pero se audita y reporta como revisión pendiente.
            self._audit("sentinel.tool_review", name, coherence_reason, "review")
            return ToolVerdict(name, tier=tier, admitted=True, reason=coherence_reason)

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

    # ------------------------------------------------------------- coherencia
    #
    # NOTA DE INVESTIGACIÓN (capa 4, antes diferida) — decisión ast_guard sí/no:
    #
    # `ast_guard.py` (``ASTGuard``) parsea CÓDIGO PYTHON con ``ast.parse()`` y
    # visita el árbol resultante para bloquear imports/llamadas/atributos
    # peligrosos (``BLOCKED_IMPORTS``/``BLOCKED_CALLS``/``BLOCKED_ATTRS``). La
    # superficie de una tool MCP (``name``/``description``/``inputSchema``) es
    # JSON declarativo — un ``inputSchema`` es un dict de JSON Schema, no una
    # expresión Python; no hay nada que ``ast.parse()`` pueda parsear ahí.
    # Reusar ``ASTGuard`` DIRECTAMENTE sobre esta superficie no aplica: falta
    # el propio objeto sobre el que opera (código fuente).
    #
    # Lo que sí se adopta de ``ast_guard`` es el PATRÓN, no el código: listas
    # de keywords declarativas + veredicto fail-closed + reason string legible
    # por violación. Esta capa aplica ese mismo patrón sobre una comparación
    # distinta — no un AST de código, sino las AFIRMACIONES en lenguaje natural
    # de ``description`` (p.ej. "solo lectura") contra las CAPACIDADES
    # declaradas por los nombres de parámetro del ``inputSchema`` (comando,
    # escritura, URL arbitraria). Decisión: lógica nueva; ``ast_guard`` no se
    # importa ni se reusa en este módulo — solo inspira la forma.
    def _vet_coherence(
        self, description: str, schema: dict[str, Any]
    ) -> tuple[str | None, bool]:
        """¿La ``description`` afirma algo verificable (p.ej. "solo lectura")
        que el ``inputSchema`` contradice? Devuelve ``(reason, strong)``:
        ``reason=None`` si es coherente o si no hay afirmación que contrastar;
        ``strong=True`` ⇒ señal fuerte (bloqueante); ``strong=False`` ⇒ señal
        débil (se admite, pero se marca para revisión — evita falsos
        positivos que romperían la adopción normal)."""
        desc = description.lower()
        if not any(kw in desc for kw in _READONLY_CLAIM_KW):
            return None, False  # nada que la description afirme y podamos contrastar

        params = self._schema_param_names(schema)

        def _matches(keywords: tuple[str, ...]) -> list[str]:
            # Nombres de PARÁMETRO reales que contienen alguna keyword de la
            # categoría, no las keywords en sí — el reason debe señalar qué
            # campo del schema es el culpable, no la lista de patrones.
            return [p for p in params if any(kw in p for kw in keywords)]

        hits = _matches(_COHERENCE_COMMAND_PARAM_KW) + _matches(_COHERENCE_WRITE_PARAM_KW)
        if hits:
            return (
                "description afirma 'solo lectura' pero inputSchema acepta "
                f"parámetro(s) de comando/escritura {hits!r}",
                True,
            )

        hits = _matches(_COHERENCE_URL_PARAM_KW)
        if hits:
            return (
                "description afirma 'solo lectura' pero inputSchema acepta "
                f"parámetro(s) de URL/endpoint {hits!r} — señal débil, revisar",
                False,
            )
        return None, False

    @classmethod
    def _schema_param_names(cls, schema: dict[str, Any]) -> list[str]:
        """Nombres de parámetro (keys de ``properties``) de un ``inputSchema``,
        recursivo sobre objetos/arrays anidados. Solo mira NOMBRES declarados,
        no valores en runtime — coherente con que esta capa opera en tiempo de
        adopción, antes de que la tool se llame ni una vez."""
        names: list[str] = []
        if not isinstance(schema, dict):
            return names
        props = schema.get("properties")
        if isinstance(props, dict):
            for key, val in props.items():
                names.append(str(key).lower())
                if isinstance(val, dict):
                    names.extend(cls._schema_param_names(val))
        items = schema.get("items")
        if isinstance(items, dict):
            names.extend(cls._schema_param_names(items))
        return names

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
                risk_level="moderate" if outcome in ("blocked", "review") else "safe",
                payload={"server": server, "detail": detail[:500]},
            )
        except Exception:  # noqa: BLE001
            pass
