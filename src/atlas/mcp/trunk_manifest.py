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
    arg_kind: str          # "db" | "repo" | "base" | "" (sin path arg) — qué ruta recibe
    tools: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()


def native_roots() -> list[RootSpec]:
    """Las raíces construidas (F1–F3 + grafo). Fuente única de la superficie del tronco."""
    return [
        RootSpec(
            "atlas-memory",
            "atlas.mcp.memory_server",
            "db",
            tools=(
                "recall",
                "add",
                "add_from_knowledge_src",
                "add_from_user_preference",
                "supersede",
                "recall_multihop",
                "shred",
            ),
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
            tools=("wikipedia_lookup", "ingest_wikipedia", "worldbank_lookup", "ingest_worldbank",
                   "ingest_open_meteo", "ingest_frankfurter"),
        ),
        RootSpec(
            # Grafo vivo del proyecto (Kuzu). Sin path arg: el server resuelve
            # DEFAULT_GRAPH_DB él mismo (la BD vive fuera del save_dir del tronco).
            "atlas-graph",
            "atlas.mcp.graph_server",
            "",
            tools=(
                "graph_overview",
                "graph_importers",
                "graph_blast_radius",
                "graph_lineage",
                "graph_churn",
                "graph_imports_of",
                "graph_note_neighborhood",
                "graph_callers",
                "graph_callees",
            ),
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
        args = ["-m", root.module]
        if root.arg_kind:
            args.append(arg_for[root.arg_kind])
        servers[root.name] = {"command": exe, "args": args}
    return {"mcpServers": servers}


def tool_overhead() -> int:
    """Cuántas tools ve el cliente sumando las raíces nativas. Mide el coste de
    contexto (el problema real del kitchen-sink: cuántas tools a la vez)."""
    return sum(len(r.tools) for r in native_roots())


# ---------------------------------------------------------------------------
# Config para el tronco agregado (atlas.mcp.trunk_server)
# ---------------------------------------------------------------------------

_TRUNK_READ_ONLY_TOOLS = [
    "trunk_sectors",
    "trunk_subsectors",
    "trunk_tools",
    "trunk_kinds",
    "trunk_health",
    "trunk_catalog",
    "trunk_find",
    "trunk_recommend_stack",
    "trunk_prepare",
    "list_skills",
    "get_skill",
    "trunk_list_roots",
    "trunk_selfcheck",
    # Fail-closed en el propio trunk: solo despacha tools declaradas read_only
    # en el catálogo de su raíz — por eso el host puede marcarla 'read'.
    "trunk_invoke_readonly",
]


def atlas_mcp_config(
    *, save_dir: Path, repo_root: Path, python: str | None = None
) -> list[dict[str, object]]:
    """Devuelve la lista de un server MCP (formato mcp_servers.json) que
    arranca el tronco agregado (atlas.mcp.trunk_server).

    Args:
        save_dir:  Ruta al directorio de persistencia del tronco (~/atlas-mcp).
        repo_root: Raíz del repositorio atlas-core.
        python:    Ejecutable Python; si None, usa sys.executable.

    Returns:
        Lista con un dict listo para serializar como mcp_servers.json.
    """
    exe = python if python is not None else sys.executable
    entry: dict[str, object] = {
        "name": "atlas-trunk",
        "cmd": [exe, "-m", "atlas.mcp.trunk_server", str(save_dir), str(repo_root)],
        "read_only_tools": _TRUNK_READ_ONLY_TOOLS,
        "enabled": True,
        "timeout_seconds": 30.0,
    }
    return [entry]
