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
5. **Egress IOC runtime (``vet_call``).** Vetea CADA ``tools/call``, no solo
   la adopción -- cableado en ``McpRegistry.dispatch()``. Fail-closed tanto
   ante un IOC real como ante un fallo interno del chequeo.
6. **Re-vetting periódico.** Ver ``McpRegistry.revet_all()`` +
   ``maintenance_sentinel_revet_tick`` -- re-corre esta gate sobre servers ya
   adoptados, nunca re-arma TOFU en solitario.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atlas.mcp.config import McpServerConfig, is_valid_mcp_identifier

_log = logging.getLogger(__name__)

# Metacaracteres de shell que NUNCA deben aparecer en un token argv legítimo.
# Su presencia indica un intento de smuggling de shell en el comando del server.
_SHELL_METACHARS: tuple[str, ...] = (
    ";", "|", "$(", "`", "&&", "||", ">", "<", "\n",
)

# Suelo de IOC de incidentes confirmados, NO anulable (2026-07-23, extraído
# del concepto de claude-mcp-sentinel v3.1: "confirmed-malicious infra can't
# be allowlisted" -- ver README, seccion "Known-malicious domains"). Producción
# construye SentinelGate sin ioc_domains/ioc_commands (orchestrator.py) -- sin
# este suelo, Capa 2 (IOC) no bloqueaba NADA en producción pese a estar
# marcada ✅ en ADR-038: el mecanismo existía, la blocklist estaba vacía.
# Se UNE (nunca reemplaza) con lo que el caller inyecte.
_INCIDENT_IOC_DOMAINS: frozenset[str] = frozenset({
    # Postmark MCP backdoor, sept. 2025 (ADR-036, thehackernews.com):
    # 15 versiones limpias + 1 update envenenado que BCC'eaba cada email.
    "giftshop.club",
})
_INCIDENT_IOC_COMMANDS: frozenset[str] = frozenset()

# Módulo → nombre de servidor que Atlas mismo genera. El nombre de módulo no es
# autoridad suficiente: ``SentinelGate`` enlaza además intérprete, checkout,
# cwd y entorno del hijo antes de conceder esta excepción nativa.
_ATLAS_NATIVE_MCP_SERVERS: dict[str, str] = {
    "atlas.mcp.memory_server": "atlas-memory",
    "atlas.mcp.graph_server": "atlas-graph",
    "atlas.mcp.knowledge_server": "atlas-knowledge",
    "atlas.mcp.operating_server": "atlas-operating",
    # Entry point agregado gobernado. Sus hijos siguen pasando el Sentinel
    # independiente que build_trunk_registry() instala antes de cada spawn.
    "atlas.mcp.trunk_server": "atlas-trunk",
}
_SHELL_EXECUTABLES: frozenset[str] = frozenset({
    "sh", "bash", "dash", "zsh", "fish", "ksh", "pwsh", "powershell",
    "powershell.exe", "cmd", "cmd.exe",
})
_SHELL_EVAL_FLAGS: frozenset[str] = frozenset({
    "-c", "/c", "-command", "-encodedcommand", "-enc",
})

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


class _SnapshotIntegrityError(RuntimeError):
    """El snapshot existe, pero no es una autoridad anti-rug-pull válida."""


class SentinelGate:
    """Vetador fail-closed de servers MCP en el momento de adopción."""

    def __init__(
        self,
        snapshot_dir: Path,
        *,
        merkle_log: Callable[..., Any] | None = None,
        ioc_domains: frozenset[str] = frozenset(),
        ioc_commands: frozenset[str] = frozenset(),
        governed_repo_root: Path | None = None,
    ) -> None:
        self._snapshot_dir = Path(snapshot_dir)
        self._merkle_log = merkle_log
        # La excepción nativa solo existe cuando el caller conoce el checkout
        # que gobierna. Sin esa procedencia, ``python -m atlas...`` sigue siendo
        # un comando no probado y permanece en cuarentena.
        self._governed_repo_root = (
            self._resolve_path(governed_repo_root, require_exists=True)
            if governed_repo_root is not None
            else None
        )
        self._governed_python = self._resolve_path(
            Path(sys.executable), require_exists=True
        )
        # Union con el suelo no anulable: pasar ioc_domains=frozenset() no
        # vacía la protección contra incidentes confirmados.
        self._ioc_domains = frozenset(d.lower() for d in ioc_domains) | _INCIDENT_IOC_DOMAINS
        self._ioc_commands = frozenset(c.lower() for c in ioc_commands) | _INCIDENT_IOC_COMMANDS

    # ------------------------------------------------------------------ API

    def vet_command(self, cfg: McpServerConfig) -> str | None:
        """Capa 2, **pre-spawn**: el ``cmd`` es argv (nunca shell, ADR-035).
        Metacaracteres de shell o un comando en la IOC blocklist vetan el server
        ANTES de arrancar el subproceso. Devuelve la razón del veto o None."""
        reason = self.inspect_command_argv(cfg.cmd)
        if reason is None and not is_valid_mcp_identifier(cfg.name):
            reason = (
                "identificador MCP inválido o ambiguo; use solo letras, "
                "dígitos, '_' o '-' y nunca '__'"
            )
        if reason is None and not self._is_governed_native_command(cfg):
            reason = (
                "third-party executable sin artefacto materializado, hash, "
                "receipt e aislamiento; ejecución en cuarentena"
            )
        if reason is not None:
            self._audit("sentinel.server_vetoed", cfg.name, reason, "blocked")
        return reason

    def inspect_command_argv(self, cmd: list[str]) -> str | None:
        """Inspecciona sintaxis e IOC sin conceder autoridad de ejecución.

        Catálogos y trials necesitan distinguir un argv peligroso de un
        paquete limpio que todavía carece de staging/admisión. Este método
        solo responde a la primera pregunta. ``vet_command`` añade después
        identidad y procedencia gobernada y continúa siendo el único gate
        pre-spawn.
        """
        return self._scan_command(cmd)

    def vet_call(self, tool: str, args: dict[str, Any]) -> str | None:
        """Capa 5, **egress runtime**: vetea CADA ``tools/call`` (no solo la
        adopción) contra el mismo suelo de IOC. Re-minado de
        claude-mcp-sentinel v3.1 (su hook corre pre-tools-call en producción,
        20/20 regresión, ~30-80ms). Un fallo interno se bloquea: ante ejecución
        de terceros, protección degradada nunca equivale a permiso."""
        try:
            surface = self._tool_surface_for_call(tool, args)
            return self._scan_iocs(surface)
        except Exception:  # noqa: BLE001 — boundary de terceros, fail-closed
            reason = "fallo interno de Sentinel durante el vetting; llamada denegada"
            _log.warning(
                "SentinelGate.vet_call: el chequeo mismo falló para tool=%r -- "
                "fail-closed (llamada denegada)",
                tool, exc_info=True,
            )
            self._audit("sentinel.call_vetoed", tool, reason, "blocked")
            return reason

    @staticmethod
    def _tool_surface_for_call(tool: str, args: dict[str, Any]) -> str:
        return f"{tool} {json.dumps(args, ensure_ascii=False, default=str)}".lower()

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
        if not is_valid_mcp_identifier(cfg.name):
            return VetResult(
                server=cfg.name,
                admitted=False,
                server_reason="identificador MCP inválido o ambiguo",
            )
        if not tools:
            return VetResult(
                server=cfg.name,
                admitted=False,
                server_reason="tools/list vacío; no hay superficie analizable",
            )
        names: list[str] = []
        for tool in tools:
            name = tool.get("name")
            schema = tool.get("inputSchema", {})
            if (
                not isinstance(name, str)
                or not is_valid_mcp_identifier(name)
                or not isinstance(schema, dict)
            ):
                return VetResult(
                    server=cfg.name,
                    admitted=False,
                    server_reason="tools/list contiene una definición no analizable",
                )
            names.append(name)
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            return VetResult(
                server=cfg.name,
                admitted=False,
                server_reason=f"tools/list contiene nombres duplicados: {duplicates}",
            )

        try:
            snapshot = self._load_snapshot(cfg.name)
        except _SnapshotIntegrityError as exc:
            reason = f"integridad de snapshot inválida: {exc}"
            self._audit("sentinel.server_vetoed", cfg.name, reason, "blocked")
            return VetResult(
                server=cfg.name,
                admitted=False,
                server_reason=reason,
            )
        first_adoption = snapshot is None
        known = snapshot or {}
        missing = sorted(set(known) - set(names))
        if missing:
            reason = f"tool(s) conocidas ausentes del server: {missing}"
            self._audit("sentinel.server_vetoed", cfg.name, reason, "blocked")
            return VetResult(
                server=cfg.name,
                admitted=False,
                server_reason=reason,
            )

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
        if not cmd or not all(isinstance(token, str) and token for token in cmd):
            return "cmd vacío o no analizable"
        for token in cmd:
            for meta in _SHELL_METACHARS:
                if meta in token:
                    return f"cmd token {token!r} contiene metacaracter de shell {meta!r}"
        joined = " ".join(cmd).lower()
        ioc = self._scan_iocs(joined)
        if ioc is not None:
            return f"cmd coincide con IOC: {ioc}"
        executable = Path(cmd[0]).name.lower()
        lowered_args = {arg.lower() for arg in cmd[1:]}
        if executable in _SHELL_EXECUTABLES and lowered_args & _SHELL_EVAL_FLAGS:
            return "shell con evaluación inline no constituye un boundary argv seguro"
        return None

    @staticmethod
    def _resolve_path(value: Path | str, *, require_exists: bool) -> Path | None:
        """Devuelve una ruta absoluta canónica o ``None`` sin abrirla.

        Las rutas vienen de configuración editable; un error de resolución es
        denegación, nunca una razón para caer a una comparación de basename.
        """
        try:
            path = Path(value).expanduser()
            if not path.is_absolute():
                return None
            if require_exists:
                return path.resolve(strict=True)
            return path.resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def _has_governed_native_context(self, cfg: McpServerConfig) -> bool:
        """Prueba que el hijo no pueda sombrear el módulo Atlas a importar."""
        repo_root = self._governed_repo_root
        if repo_root is None or self._governed_python is None:
            return False
        if cfg.cwd is None or self._resolve_path(cfg.cwd, require_exists=True) != repo_root:
            return False
        # Un PATH/PYTHONPATH o secret passthrough editable puede cambiar la
        # resolución del intérprete o inyectar preload; los entrypoints propios
        # no los necesitan y deben arrancar con el entorno mínimo del registry.
        if cfg.env_extra or cfg.env_passthrough:
            return False
        return self._resolve_path(cfg.cmd[0], require_exists=True) == self._governed_python

    def _is_governed_native_command(self, cfg: McpServerConfig) -> bool:
        """Admite solo comandos nativos ligados al proceso y checkout actual.

        Una coincidencia ``python -m atlas.mcp.*`` no acredita qué bytes
        importará el subproceso. La excepción exige el mismo intérprete que
        cargó Sentinel, el checkout gobernado como cwd y sin entorno heredado
        editable; así una config MCP alterada no puede usar un ejecutable con
        nombre ``python`` ni un paquete Atlas sombreado.
        """
        cmd = cfg.cmd
        if len(cmd) < 2 or not Path(cmd[0]).name.lower().startswith("python"):
            return False
        if cmd[1] == "-m":
            if len(cmd) < 3:
                return False
            module = cmd[2]
            expected_name = _ATLAS_NATIVE_MCP_SERVERS.get(module)
            if expected_name is None or cfg.name != expected_name:
                return False
            if not self._has_governed_native_context(cfg):
                return False
            if module == "atlas.mcp.trunk_server":
                # El manifest generado es exacto: un save dir absoluto y el
                # checkout gobernado como último argumento. Nada adicional se
                # interpreta silenciosamente por el entrypoint CLI.
                return (
                    len(cmd) == 5
                    and self._resolve_path(cmd[3], require_exists=False) is not None
                    and self._resolve_path(cmd[4], require_exists=True)
                    == self._governed_repo_root
                )
            # Cada raíz nativa recibe exactamente un argumento de datos. Las
            # raíces que operan sobre código deben recibir el mismo checkout;
            # las de memoria/conocimiento pueden usar su almacenamiento local.
            if len(cmd) != 4 or self._resolve_path(cmd[3], require_exists=False) is None:
                return False
            if module in {"atlas.mcp.graph_server", "atlas.mcp.operating_server"}:
                return self._resolve_path(cmd[3], require_exists=True) == self._governed_repo_root
            return True
        script = Path(cmd[1])
        tracked_fixture = (
            Path(__file__).resolve().parents[3]
            / "tests"
            / "fixtures"
            / "mcp_echo_server.py"
        )
        # Fixture trackeado, permitido únicamente para los smokes locales.
        return (
            script.name == "mcp_echo_server.py"
            and script.resolve() == tracked_fixture
        )

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
            return None  # esperado: primera adopción real, sin señal que dar
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning(
                "SentinelGate: snapshot corrupto para %r en %s -- adopción "
                "bloqueada (protección anti rug-pull fail-closed)",
                server, path,
            )
            raise _SnapshotIntegrityError("no se puede leer o parsear") from exc
        if not isinstance(data, dict):
            _log.warning(
                "SentinelGate: snapshot corrupto para %r en %s -- raíz no "
                "mapping; adopción bloqueada",
                server, path,
            )
            raise _SnapshotIntegrityError("la raíz JSON no es un objeto")
        snapshot: dict[str, str] = {}
        for key, value in data.items():
            if (
                not isinstance(key, str)
                or not key
                or not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value.lower())
            ):
                _log.warning(
                    "SentinelGate: snapshot corrupto para %r en %s -- entrada "
                    "inválida; adopción bloqueada",
                    server, path,
                )
                raise _SnapshotIntegrityError("contiene una entrada inválida")
            snapshot[key] = value
        return snapshot

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
