"""Config de servidores MCP — ADR-035 dec.7.

Modelo de datos + loader desde ``mcp_servers.json``. Secretos NUNCA viven
en el JSON: cada server declara los nombres de las env vars que necesita
(``env_passthrough``), y el loader las copia del entorno del proceso al
``env`` con el que arrancará el subproceso. Si la env var no está
definida, el server se marca disabled (fail-safe — no arranque sin
credenciales).

NUNCA loggear ``env`` (contiene secretos resueltos).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class McpServerConfig:
    """Configuración inmutable de un server MCP.

    - ``name``: identificador estable (forma parte de ``mcp__<name>__<tool>``).
    - ``cmd``: argv del subproceso (lista — nunca string para shell).
    - ``cwd``: directorio de trabajo opcional.
    - ``env_passthrough``: nombres de env vars del proceso padre a copiar al
      hijo (típicamente API keys). Las que faltan se loggean como missing.
    - ``env_extra``: env vars no-secretas (paths, locale).
    - ``read_only_tools``: nombres (sin prefijo) que se consideran de lectura
      → corren inline. El resto son mutate por defecto → HITL.
    - ``enabled``: si False, el registry lo ignora.
    - ``timeout_seconds``: budget por request.
    """

    name: str
    cmd: list[str]
    cwd: str | None = None
    env_passthrough: list[str] = field(default_factory=list)
    env_extra: dict[str, str] = field(default_factory=dict)
    read_only_tools: list[str] = field(default_factory=list)
    enabled: bool = True
    timeout_seconds: float = 15.0

    def resolve_env(self) -> tuple[dict[str, str], list[str]]:
        """Resuelve ``env`` para el subproceso. Devuelve (env, missing).

        ``env`` incluye PATH para que se encuentren binarios estándar pero
        no propaga el resto del entorno (privilegio mínimo). NUNCA debe
        loggearse — contiene secretos.
        """
        env: dict[str, str] = {}
        path = os.environ.get("PATH")
        if path:
            env["PATH"] = path
        env.update(self.env_extra)
        missing: list[str] = []
        for var in self.env_passthrough:
            val = os.environ.get(var)
            if val is None:
                missing.append(var)
            else:
                env[var] = val
        return env, missing


def load_servers(path: Path | str) -> list[McpServerConfig]:
    """Carga la lista de servers desde JSON. Devuelve [] si el archivo no
    existe (no es error — Atlas funciona sin MCP)."""
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON array of server configs")
    servers: list[McpServerConfig] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: each server must be a JSON object")
        servers.append(
            McpServerConfig(
                name=str(entry["name"]),
                cmd=list(entry["cmd"]),
                cwd=entry.get("cwd"),
                env_passthrough=list(entry.get("env_passthrough", [])),
                env_extra=dict(entry.get("env_extra", {})),
                read_only_tools=list(entry.get("read_only_tools", [])),
                enabled=bool(entry.get("enabled", True)),
                timeout_seconds=float(entry.get("timeout_seconds", 15.0)),
            )
        )
    return servers


def save_servers(path: Path | str, configs: list[McpServerConfig]) -> None:
    """Persiste ``configs`` como JSON en el mismo formato que ``load_servers``
    lee. Nunca escribe secretos: ``env_passthrough`` guarda solo NOMBRES de
    env vars, ``env_extra`` es explícitamente no-secreta (ver docstring del
    dataclass) — igual que el fichero que ya se edita a mano hoy."""
    raw = [
        {
            "name": cfg.name,
            "cmd": cfg.cmd,
            "cwd": cfg.cwd,
            "env_passthrough": cfg.env_passthrough,
            "env_extra": cfg.env_extra,
            "read_only_tools": cfg.read_only_tools,
            "enabled": cfg.enabled,
            "timeout_seconds": cfg.timeout_seconds,
        }
        for cfg in configs
    ]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
