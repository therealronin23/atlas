"""
Atlas Core — Pieza 2c: probe de spawn MCP (initialize + tools/list).

Honesto:
  - ``npx``/``uvx``/``npm`` requieren bootstrap de red → spawn omitido (argv vet en 2b).
  - Raíces ``atlas.mcp.*`` pueden probarse offline con PYTHONPATH + jaula bwrap.
  - NO promueve a ``verificado`` — solo refuerza ``probado-en-jaula``.
"""

from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, cast

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.config import McpServerConfig
from atlas.mcp.transport import McpTransport, StdioTransport

_PROTOCOL_VERSION = "2025-06-18"
_NETWORK_BOOTSTRAP = frozenset(
    {"npx", "npm", "uvx", "uv", "node", "curl", "wget", "git", "pnpm", "yarn"}
)
_ATLAS_MCP_PREFIX = "atlas.mcp."


class _ProbeTransport(McpTransport, Protocol):
    def start(self) -> None: ...


class _TransportFactory(Protocol):
    def __call__(self, cmd: list[str], env: dict[str, str] | None) -> _ProbeTransport: ...


def requires_network_bootstrap(cmd: list[str]) -> bool:
    """True si el argv probablemente necesita red para arrancar (npx/uvx/…)."""
    if not cmd:
        return True
    return Path(cmd[0]).name.lower() in _NETWORK_BOOTSTRAP


def is_atlas_native_module(cmd: list[str]) -> bool:
    try:
        idx = cmd.index("-m")
    except ValueError:
        return False
    if idx + 1 >= len(cmd):
        return False
    return str(cmd[idx + 1]).startswith(_ATLAS_MCP_PREFIX)


def catalog_entry_to_cmd(entry: CatalogEntry) -> list[str]:
    raw = entry.install.strip()
    if not raw:
        return []
    return shlex.split(raw)


def build_mcp_bwrap_argv(
    bwrap_bin: str,
    cmd: list[str],
    *,
    src_root: Path,
    work_dir: Path,
) -> list[str]:
    """Envuelve ``cmd`` en bwrap sin red. Monta ``src_root`` ro como PYTHONPATH."""
    src_in_jail = "/tmp/atlas_src"
    work_in_jail = "/tmp/atlas_work"
    argv = [
        bwrap_bin,
        "--unshare-all",
        "--cap-drop",
        "ALL",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/etc/ssl",
        "/etc/ssl",
        "--ro-bind",
        str(src_root),
        src_in_jail,
        "--bind",
        str(work_dir),
        work_in_jail,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--die-with-parent",
        "--new-session",
        "--",
        "env",
        f"PYTHONPATH={src_in_jail}",
        "HOME=/tmp/atlas_work",
        *cmd,
    ]
    return argv


def _rewrite_paths_for_jail(cmd: list[str], work_dir: Path) -> list[str]:
    """Reescribe paths absolutos del host al workdir montado en la jaula."""
    work = str(work_dir)
    jail_work = "/tmp/atlas_work"
    out: list[str] = []
    for arg in cmd:
        if arg.startswith(work):
            out.append(jail_work + arg[len(work) :])
        else:
            out.append(arg)
    return out


@dataclass(frozen=True)
class SpawnProbeResult:
    ok: bool
    skipped: bool
    tool_count: int
    jailed: bool
    reason: str


def probe_mcp_stdio(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout_seconds: float = 20.0,
    transport_factory: _TransportFactory | None = None,
) -> SpawnProbeResult:
    """Handshake MCP mínimo: initialize → tools/list."""
    if not cmd:
        return SpawnProbeResult(
            ok=False, skipped=False, tool_count=0, jailed=False, reason="cmd vacío"
        )
    factory = transport_factory or (
        lambda c, e: StdioTransport(cmd=c, env=e, cwd=cwd, timeout_seconds=timeout_seconds)
    )
    transport = factory(cmd, env)
    try:
        transport.start()
        init = transport.request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "atlas-spawn-trial", "version": "0"},
            },
        )
        if not isinstance(init, dict):
            return SpawnProbeResult(
                ok=False,
                skipped=False,
                tool_count=0,
                jailed=False,
                reason="initialize: respuesta no dict",
            )
        transport.notify("notifications/initialized", {})
        tools_resp = transport.request("tools/list", {})
        tools = (tools_resp or {}).get("tools", []) if isinstance(tools_resp, dict) else []
        if not isinstance(tools, list):
            tools = []
        return SpawnProbeResult(
            ok=True,
            skipped=False,
            tool_count=len(tools),
            jailed=False,
            reason=f"spawn OK ({len(tools)} tools)",
        )
    except Exception as exc:  # noqa: BLE001
        return SpawnProbeResult(
            ok=False,
            skipped=False,
            tool_count=0,
            jailed=False,
            reason=f"spawn falló: {exc}"[:240],
        )
    finally:
        transport.close()


class SpawnTrial:
    """Probe injectable para TrialGate (tests usan transport_factory)."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        work_dir: Path | None = None,
        use_jail: bool = True,
        transport_factory: _TransportFactory | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._repo_root = repo_root
        self._work_dir = work_dir
        self._use_jail = use_jail
        self._transport_factory = transport_factory
        self._timeout = timeout_seconds

    def probe_cmd(self, cmd: list[str]) -> SpawnProbeResult:
        if requires_network_bootstrap(cmd):
            return SpawnProbeResult(
                ok=False,
                skipped=True,
                tool_count=0,
                jailed=False,
                reason="bootstrap de red (spawn omitido)",
            )

        if (
            self._use_jail
            and self._repo_root is not None
            and self._work_dir is not None
            and is_atlas_native_module(cmd)
        ):
            jailed = self._probe_jailed(cmd)
            if jailed is not None:
                return jailed

        return probe_mcp_stdio(
            cmd,
            timeout_seconds=self._timeout,
            transport_factory=self._transport_factory,
        )

    def probe_entry(self, entry: CatalogEntry) -> SpawnProbeResult:
        return self.probe_cmd(catalog_entry_to_cmd(entry))

    def _probe_jailed(self, cmd: list[str]) -> SpawnProbeResult | None:
        from atlas.security.bwrap_jail import BwrapJail

        if not BwrapJail.is_available():
            return None
        bwrap = shutil.which("bwrap")
        if bwrap is None or self._repo_root is None or self._work_dir is None:
            return None
        src = self._repo_root / "src"
        if not src.is_dir():
            return None

        self._work_dir.mkdir(parents=True, exist_ok=True)
        jailed_cmd = _rewrite_paths_for_jail(cmd, self._work_dir)
        argv = build_mcp_bwrap_argv(bwrap, jailed_cmd, src_root=src, work_dir=self._work_dir)
        timeout = self._timeout

        def _factory(_cmd: list[str], _env: dict[str, str] | None) -> _ProbeTransport:
            return StdioTransport(cmd=argv, env=_env, timeout_seconds=timeout)

        result = probe_mcp_stdio(
            argv,
            transport_factory=cast(_TransportFactory, _factory),
        )
        if result.ok:
            return SpawnProbeResult(
                ok=True,
                skipped=False,
                tool_count=result.tool_count,
                jailed=True,
                reason=f"spawn jaula OK ({result.tool_count} tools)",
            )
        return SpawnProbeResult(
            ok=False,
            skipped=False,
            tool_count=0,
            jailed=True,
            reason=result.reason,
        )


@dataclass(frozen=True)
class QuarantineCandidate:
    name: str
    kind: str
    reason: str
    action: str  # quarantine | retry


def graduated_quarantine(
    *,
    name: str,
    kind: str,
    reason: str,
) -> QuarantineCandidate | None:
    """Saneamiento graduado: fallos de supply-chain → cuarentena; resto → retry."""
    low = reason.lower()
    supply_chain = (
        "metacaracter",
        "eval()",
        "exec()",
        "__import__",
        "os.system",
        "subprocess",
        "veto",
        "vetado",
        "ioc",
    )
    if any(marker in low for marker in supply_chain):
        return QuarantineCandidate(name=name, kind=kind, reason=reason, action="quarantine")
    if "spawn falló" in low or "timeout" in low:
        return QuarantineCandidate(name=name, kind=kind, reason=reason, action="retry")
    return None


def mcp_config_from_entry(entry: CatalogEntry) -> McpServerConfig | None:
    cmd = catalog_entry_to_cmd(entry)
    if not cmd:
        return None
    return McpServerConfig(name=entry.name, cmd=cmd)
