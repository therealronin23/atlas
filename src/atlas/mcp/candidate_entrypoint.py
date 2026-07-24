"""Descubre el comando de arranque real de un candidato ``stdio`` extraído
(sin instalar -- no hay console-script generado por ``pip install``/``npm
install``, deliberadamente, ver ``candidate_fetch.py``).

Fail-closed (I6 de ADR-075): adivinar el entry point equivocado de un
paquete de terceros podría invocar código no pretendido o dar un falso
"protocolo falló". Si hay ambigüedad real (2+ candidatos sin patrón claro),
se rechaza explícito -- "no determinable" en vez de adivinar.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PypiEntrypoint:
    ok: bool
    module: str = ""
    function: str = ""
    reason: str = ""


@dataclass(frozen=True)
class NpmEntrypoint:
    ok: bool
    script_path: str = ""
    reason: str = ""


def discover_pypi_entrypoint(source_dir: Path, *, package_identifier: str) -> PypiEntrypoint:
    """Lee ``[project.scripts]`` de ``pyproject.toml``. Prefiere el script
    ``<identifier>-server`` (patrón real observado: el server MCP se nombra
    distinto del CLI de usuario). Con un único script, lo usa directo. Con
    2+ scripts y ninguno coincide con el patrón esperado: ambiguo,
    fail-closed."""
    pyproject = source_dir / "pyproject.toml"
    if not pyproject.is_file():
        return PypiEntrypoint(ok=False, reason="pyproject.toml no encontrado")
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return PypiEntrypoint(ok=False, reason=f"pyproject.toml malformado: {exc}")

    scripts: dict[str, str] = (data.get("project") or {}).get("scripts") or {}
    if not scripts:
        return PypiEntrypoint(ok=False, reason="sin [project.scripts] declarados")

    def _split(target: str) -> tuple[str, str]:
        module, _, func = target.partition(":")
        return module, func or "main"

    server_key = f"{package_identifier}-server"
    if server_key in scripts:
        module, func = _split(scripts[server_key])
        return PypiEntrypoint(ok=True, module=module, function=func, reason="ok")

    if len(scripts) == 1:
        (only_target,) = scripts.values()
        module, func = _split(only_target)
        return PypiEntrypoint(ok=True, module=module, function=func, reason="ok")

    return PypiEntrypoint(
        ok=False,
        reason=f"ambiguo: {len(scripts)} scripts declarados ({sorted(scripts)!r}), ninguno coincide con '{server_key}'",
    )


def discover_npm_entrypoint(source_dir: Path, *, package_identifier: str) -> NpmEntrypoint:
    """Lee ``bin`` de ``package.json``: string = un solo binario (caso común
    para un server MCP simple); dict = varios, se acepta solo si una clave
    coincide con un patrón claro derivado del identifier."""
    pkg_json = source_dir / "package.json"
    if not pkg_json.is_file():
        return NpmEntrypoint(ok=False, reason="package.json no encontrado")
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return NpmEntrypoint(ok=False, reason=f"package.json malformado: {exc}")

    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        return NpmEntrypoint(ok=True, script_path=bin_field, reason="ok")
    if isinstance(bin_field, dict):
        short_name = package_identifier.rsplit("/", 1)[-1]
        for key in (short_name, f"{short_name}-mcp", f"{short_name}-server"):
            if key in bin_field:
                return NpmEntrypoint(ok=True, script_path=str(bin_field[key]), reason="ok")
        return NpmEntrypoint(
            ok=False,
            reason=f"ambiguo: {len(bin_field)} binarios declarados ({sorted(bin_field)!r}), ninguno coincide",
        )
    return NpmEntrypoint(ok=False, reason="sin 'bin' declarado en package.json")
