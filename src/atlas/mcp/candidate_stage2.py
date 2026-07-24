"""Orquestación real de la etapa 2 de ADR-075 (2A stdio / 2B http).

Cada paso es fail-closed en cadena: si un paso falla, los siguientes NO se
intentan y ``completed=False`` -- nunca se finge éxito parcial como si fuera
completo. ``stage_reached`` dice exactamente hasta dónde llegó, para que un
fallo temprano (paquete no encontrado) no se confunda con uno tardío
(hallazgos de seguridad reales).

2A NO incluye ejecución en sandbox del server extraído (límite reconocido
2026-07-24: requeriría instalar las dependencias del paquete, ejecutando
código de build no confiable ANTES de terminar de vetarlo -- decisión de
nivel ADR, no improvisada). Cubre: lookup -> descarga verificada ->
extracción segura -> entry point -> análisis estático (semgrep).
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from atlas.core.adversarial_panel import Severity
from atlas.mcp.candidate_entrypoint import discover_npm_entrypoint, discover_pypi_entrypoint
from atlas.mcp.candidate_fetch import download_and_verify, safe_extract
from atlas.mcp.candidate_package_lookup import PackageLookupResult, lookup_package
from atlas.mcp.candidate_static_scan import StaticFinding, scan_source
from atlas.mcp.http_mcp_transport import HttpMcpTransport
from atlas.mcp.transport import McpProtocolError


def _default_binary_fetcher(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "atlas-core-vetting-probe"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


@dataclass(frozen=True)
class Stage2AResult:
    name: str
    completed: bool
    stage_reached: str  # lookup|fetch|extract|entrypoint|static_scan
    reason: str = ""
    entrypoint_module: str = ""
    entrypoint_function: str = ""
    static_findings: list[StaticFinding] = field(default_factory=list)

    @property
    def worst_severity(self) -> Severity:
        return max((f.severity for f in self.static_findings), default=Severity.NONE)


def run_stage2a_stdio(
    entry: dict[str, Any],
    *,
    quarantine_root: Path,
    lookup_fn: Callable[..., PackageLookupResult] = lookup_package,
    binary_fetcher: Callable[[str], tuple[int, bytes]] = _default_binary_fetcher,
    semgrep_runner: Any = None,
) -> Stage2AResult:
    name = str(entry.get("name", ""))
    registry = str(entry.get("package_registry", ""))
    identifier = str(entry.get("package_identifier", ""))
    version = str(entry.get("version", ""))

    lookup = lookup_fn(registry, identifier, version)
    if not lookup.exists or not lookup.version_matches or not lookup.download_url:
        return Stage2AResult(name=name, completed=False, stage_reached="lookup", reason=lookup.reason)

    safe_name = identifier.replace("/", "_").replace("@", "")
    dest_dir = quarantine_root / safe_name
    archive_path = dest_dir / "archive"
    allowed_domain = "files.pythonhosted.org" if registry == "pypi" else "registry.npmjs.org"
    fetch = download_and_verify(
        lookup.download_url, lookup.sha256, archive_path,
        fetcher=binary_fetcher, allowed_domain=allowed_domain,
    )
    if not fetch.ok:
        return Stage2AResult(name=name, completed=False, stage_reached="fetch", reason=fetch.reason)

    extract_dir = dest_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    # El nombre del archivo no lleva extensión real (download_and_verify no la
    # preserva) -- safe_extract despacha por contenido probando tar primero.
    archive_named = archive_path.with_suffix(".tar.gz" if registry == "pypi" else ".zip")
    archive_path.rename(archive_named)
    extract = safe_extract(archive_named, extract_dir)
    if not extract.ok:
        return Stage2AResult(name=name, completed=False, stage_reached="extract", reason=extract.reason)

    # El contenido puede quedar anidado en un único subdirectorio raíz
    # (convención habitual de sdists/tarballs: "adeu-1.5.2/...").
    roots = [p for p in extract_dir.iterdir() if p.is_dir()]
    source_dir = roots[0] if len(roots) == 1 else extract_dir

    if registry == "pypi":
        ep = discover_pypi_entrypoint(source_dir, package_identifier=identifier)
        ep_module, ep_function, ep_ok, ep_reason = ep.module, ep.function, ep.ok, ep.reason
    else:
        npm_ep = discover_npm_entrypoint(source_dir, package_identifier=identifier)
        ep_module, ep_function, ep_ok, ep_reason = npm_ep.script_path, "", npm_ep.ok, npm_ep.reason
    if not ep_ok:
        return Stage2AResult(name=name, completed=False, stage_reached="entrypoint", reason=ep_reason)

    scan_kwargs: dict[str, Any] = {}
    if semgrep_runner is not None:
        scan_kwargs["runner"] = semgrep_runner
    scan = scan_source(str(source_dir), **scan_kwargs)
    if not scan.ok:
        return Stage2AResult(name=name, completed=False, stage_reached="static_scan", reason=scan.reason)

    return Stage2AResult(
        name=name, completed=True, stage_reached="static_scan", reason="ok",
        entrypoint_module=ep_module, entrypoint_function=ep_function,
        static_findings=scan.findings,
    )


@dataclass(frozen=True)
class Stage2BResult:
    name: str
    completed: bool
    reason: str = ""
    tool_count: int = 0


def run_stage2b_http(entry: dict[str, Any], *, fetcher: Any, timeout_seconds: float = 8.0) -> Stage2BResult:
    name = str(entry.get("name", ""))
    remote_url = str(entry.get("remote_url", ""))
    if not remote_url:
        return Stage2BResult(name=name, completed=False, reason="sin remote_url -- nada que sondear")

    t = HttpMcpTransport(remote_url, fetcher=fetcher, timeout_seconds=timeout_seconds)
    try:
        t.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "atlas-vetting-probe", "version": "0"},
        })
        t.notify("notifications/initialized", {})
        tools_result = t.request("tools/list", {})
    except McpProtocolError as exc:
        return Stage2BResult(name=name, completed=False, reason=str(exc))

    tools = (tools_result or {}).get("tools", []) if isinstance(tools_result, dict) else []
    return Stage2BResult(name=name, completed=True, reason="ok", tool_count=len(tools) if isinstance(tools, list) else 0)
