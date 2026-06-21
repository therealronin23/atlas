"""
Atlas Core — TrunkManifest: agregación de las raíces nativas (MCP trunk, F4).

Declara las raíces que construimos (memory/operating/knowledge) y emite una config
de cliente MCP unificada: el "tronco = una conexión". Cada raíz es un proceso stdio
independalente (políglota por-raíz, F5), así que el tronco práctico es la config que
las agrupa + la superficie PEQUEÑA de tools (anti-kitchen-sink).

Honesto: la arquitectura tronco+raíces es commodity; el valor es el contenido. Las
raíces commodity (filesystem/git) son off-the-shelf y se añaden por el instalador,
no se reinventan aquí.

Diseño: docs/design/mcp_trunk_portable.md (F4).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RootSpec:
    name: str
    module: str            # módulo ejecutable: python -m <module>
    arg_kind: str          # "db" | "repo" | "base" — qué ruta recibe
    tools: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()


def native_roots() -> list[RootSpec]:
    """Las 3 raíces construidas (F1–F3). Fuente única de la superficie del tronco."""
    return [
        RootSpec(
            "atlas-memory",
            "atlas.mcp.memory_server",
            "db",
            tools=("recall", "add", "supersede"),
        ),
        RootSpec(
            "atlas-operating",
            "atlas.mcp.operating_server",
            "repo",
            tools=("sanitation_audit",),
            resources=("operating://agents", "operating://ledger"),
        ),
        RootSpec(
            "atlas-knowledge",
            "atlas.mcp.knowledge_server",
            "base",
            tools=("wikipedia_lookup", "ingest_wikipedia"),
        ),
    ]


def client_config(
    *, memory_db: Path, repo_root: Path, knowledge_base: Path, python: str | None = None
) -> dict[str, object]:
    """Config de cliente MCP (formato `mcpServers`) que conecta las 3 raíces de
    una. Las rutas son el 'save file' (capa neutra) que da el cross-play."""
    exe = python if python is not None else sys.executable
    arg_for = {
        "db": str(memory_db),
        "repo": str(repo_root),
        "base": str(knowledge_base),
    }
    servers: dict[str, object] = {}
    for root in native_roots():
        servers[root.name] = {
            "command": exe,
            "args": ["-m", root.module, arg_for[root.arg_kind]],
        }
    return {"mcpServers": servers}


def tool_overhead() -> int:
    """Cuántas tools ve el cliente sumando las raíces nativas. Mide el coste de
    contexto (el problema real del kitchen-sink: cuántas tools a la vez)."""
    return sum(len(r.tools) for r in native_roots())
