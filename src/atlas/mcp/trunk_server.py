"""
Atlas Core — Shell FastMCP del TRONCO-AGREGADOR (línea B).

Expone una superficie META PEQUEÑA (anti-kitchen-sink): el cliente se conecta a
UN solo server (el tronco) y ve 3 tools de navegación lazy en vez de las N tools
de todas las raíces:
  - trunk_sectors()        → índice de sectores (nivel 1)
  - trunk_tools(sector)    → tools del sector (nivel 2, drill-down)
  - trunk_invoke(tool,args)→ ejecuta una tool, enrutada a su raíz dueña

SDK `mcp` opcional ([mcp]); import diferido. El dispatcher real (McpRegistry, con
Merkle + SentinelGate) se inyecta al construir el TrunkAggregator.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.mcp.config import McpServerConfig


def load_secrets_env(path: Path) -> dict[str, str]:
    """Lee un fichero .env de secretos y devuelve {KEY: VALUE}.

    Acepta ``export KEY="VALUE"`` y ``KEY=VALUE``; ignora comentarios y líneas
    vacías; quita comillas envolventes (dobles o simples).  Si el fichero no
    existe devuelve {}.  Los valores NO se loggean (secretos).
    """
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Quita prefijo "export " opcional
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Quita comillas envolventes dobles o simples
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            result[key] = value
    return result
from atlas.mcp.trunk_aggregator import TrunkAggregator
from atlas.mcp.trunk_manifest import native_roots

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from atlas.mcp.catalog import CatalogEntry
    from atlas.mcp.skills_store import SkillStore


def root_configs(
    *, save_dir: Path, repo_root: Path, python: str | None = None
) -> list[McpServerConfig]:
    """McpServerConfig por raíz nativa: el tronco las spawnea como hijos stdio.
    El save (memoria/knowledge) en la capa neutra; operating apunta al repo."""
    exe = python if python is not None else sys.executable
    arg_for = {
        "db": str(Path(save_dir) / "memory.db"),
        "repo": str(repo_root),
        "base": str(Path(save_dir) / "kb"),
    }
    return [
        McpServerConfig(
            name=root.name,
            cmd=[exe, "-m", root.module, arg_for[root.arg_kind]],
            # recall/lookup/audit son de lectura; el resto mutan (HITL).
            read_only_tools=[t for t in root.tools if t.startswith(("recall", "wikipedia_lookup", "worldbank_lookup", "sanitation"))],
        )
        for root in native_roots()
    ]


def servers_from_registry(registry: Any) -> dict[str, list[str]]:
    """Mapa server → tools de lo realmente CONECTADO, parseando los nombres
    namespaced `mcp__<server>__<tool>` de `registry.tool_specs()`. Así el
    agregador indexa también los MCP externos, no solo native_roots."""
    out: dict[str, list[str]] = {}
    for spec in registry.tool_specs():
        full = spec.get("function", {}).get("name", "")
        parts = full.split("__")
        if len(parts) >= 3 and parts[0] == "mcp":
            out.setdefault(parts[1], []).append("__".join(parts[2:]))
    return out


def trunk_children(
    catalog: list["CatalogEntry"], *, save_dir: Path, repo_root: Path, python: str | None = None
) -> list[McpServerConfig]:
    """Hijos del tronco DERIVADOS DEL CATÁLOGO (paso 2): toda entrada conectable
    (kind=mcp, mode=connected, status instalado|verificado). Las raíces NUESTRAS
    (source=atlas.mcp.*) resuelven su comando con path arg; las EXTERNAS usan su
    campo `install`. Así un MCP externo verificado entra al tronco sin tocar código.
    Excluye candidatos (wire-before-claim) y lo `served` (skills/APIs, no se conectan)."""
    by_module = {r.module: r for r in native_roots()}
    our_cfgs = {c.cmd[c.cmd.index("-m") + 1]: c
                for c in root_configs(save_dir=save_dir, repo_root=repo_root, python=python)}
    out: list[McpServerConfig] = []
    for e in catalog:
        if e.kind != "mcp" or e.mode != "connected" or e.status not in {"instalado", "verificado"}:
            continue
        if e.source in by_module:  # raíz nuestra → comando ya resuelto con path arg
            out.append(our_cfgs[e.source])
        elif e.install.strip():    # externa → comando de su `install`
            out.append(McpServerConfig(
                name=e.name, cmd=shlex.split(e.install),
                env_passthrough=list(e.env_passthrough),  # secretos por entorno, no en cmd
            ))
    return out


def build_trunk_server(
    agg: TrunkAggregator,
    *,
    name: str = "atlas-trunk",
    skill_store: "SkillStore | None" = None,
    catalog: "list[CatalogEntry] | None" = None,
    taxonomy: dict[str, Any] | None = None,
) -> "FastMCP":
    """Servidor FastMCP que expone la fachada meta lazy del tronco (navegación de 3
    niveles + buscador). Con `skill_store` sirve skills; con `catalog`+`taxonomy`
    expone `trunk_subsectors` y `trunk_find` (salto directo, sin manual)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def trunk_sectors() -> list[dict[str, Any]]:
        """Índice de sectores (nivel 1, pequeño): empieza SIEMPRE por aquí."""
        return agg.sectors()

    @server.tool()
    def trunk_tools(sector: str, subsector: str | None = None) -> list[dict[str, Any]]:
        """Tools de un sector (nivel 3): opcionalmente filtra por subsector."""
        return agg.tools_in(sector, subsector)

    @server.tool()
    def trunk_invoke(tool: str, args: dict[str, Any] | None = None) -> Any:
        """Ejecuta una tool, enrutada a su raíz dueña (con audit/seguridad detrás)."""
        return agg.invoke(tool, args or {})

    if taxonomy is not None:
        @server.tool()
        def trunk_subsectors(sector: str) -> list[dict[str, Any]]:
            """Subsectores de un sector (nivel 2): el mapa fino, sin manual."""
            sub = (taxonomy.get(sector) or {}).get("subsectors", {})
            return [{"id": sid, "label": s["label"]} for sid, s in sub.items()]

    if catalog is not None:
        from atlas.mcp.catalog import by_kind as _by_kind

        @server.tool()
        def trunk_kinds() -> dict[str, int]:
            """Las LÍNEAS del catálogo (kind→cuántos): mcp, skill, api, tool, prompt,
            hook, subagent, plugin, rule, workflow. Cada línea es un 'StormMCP'."""
            return _by_kind(catalog)

        @server.tool()
        def trunk_catalog(kind: str | None = None, sector: str | None = None) -> list[dict[str, Any]]:
            """Explora una LÍNEA (kind) y/o un dominio (sector): nombre, sector,
            estado, mode. Madurez-first. Incluye candidatos (descubrimiento)."""
            _MAT = {"instalado": 0, "verificado": 1, "candidato": 2}
            rows = [
                {"name": e.name, "sector": e.sector, "subsector": e.subsector,
                 "kind": e.kind, "status": e.status, "mode": e.mode}
                for e in catalog
                if (kind is None or e.kind == kind) and (sector is None or e.sector == sector)
            ]
            rows.sort(key=lambda r: (_MAT.get(r["status"], 3), r["name"].lower()))
            return rows

    if catalog is not None and taxonomy is not None:
        from atlas.mcp.catalog import find as _find

        @server.tool()
        def trunk_find(query: str) -> list[dict[str, Any]]:
            """Salto directo: busca por nombre/alias (p.ej. 'seguridad', 'figma') y
            devuelve el camino sector/subsector, madurez-first. No hace falta navegar."""
            return _find(catalog, taxonomy, query)

    if skill_store is not None:
        @server.tool()
        def list_skills() -> list[str]:
            """Skills servidos por el tronco (sin descarga)."""
            return skill_store.list_skills()

        @server.tool()
        def get_skill(name: str) -> str:
            """Devuelve el contenido de un skill (markdown). Acceso 'de una', sin instalar."""
            return skill_store.get(name)

    return server


def serve(*, save_dir: Path, repo_root: Path, name: str = "atlas-trunk") -> None:
    """Entry stdio del tronco: construye el McpRegistry PEREZOSO (sin start_all),
    frontea con descubrimiento lazy por sector y sirve UNA conexión stdio.

    Spawn perezoso: los MCP externos (npx/uvx) NO se arrancan al conectar; cada
    raíz se levanta al PRIMER dispatch de una de sus tools. El índice de sectores
    y herramientas en trunk_sectors/trunk_tools se construye con las raíces
    nativas estáticas (native_roots); los externos aparecen al invocarse.

    Trade-off documentado: cero spawns/descargas al conectar; las tools de MCP
    externos no son visibles en trunk_tools hasta que se haya invocado al menos
    una vez su server dueño."""
    import os

    from atlas.mcp.catalog import load_catalog, load_taxonomy
    from atlas.mcp.registry import McpRegistry

    # Carga credenciales del fichero de secretos LOCAL (nunca en git/catálogo).
    # Usa setdefault para no pisar vars ya presentes en el entorno real.
    # Permite que los MCP externos con env_passthrough (p.ej. google-workspace)
    # encuentren sus secretos cuando el tronco los frontea.
    _secrets_path = Path.home() / ".config" / "atlas-mcp" / "secrets.env"
    for _k, _v in load_secrets_env(_secrets_path).items():
        os.environ.setdefault(_k, _v)

    catalog_path = Path(repo_root) / "docs" / "design" / "mcp_catalog.yaml"
    catalog = load_catalog(catalog_path)
    taxonomy = load_taxonomy(catalog_path)
    # Browse poblado: añade lo sembrado+clasificado (todo candidato → trunk_children
    # lo ignora; solo enriquece trunk_catalog/find/kinds). "En todas partes".
    classified = Path(repo_root) / "docs" / "design" / "mcp_catalog_classified.yaml"
    if classified.is_file():
        catalog = catalog + load_catalog(classified)
    # Hijos DERIVADOS DEL CATÁLOGO (paso 2): nuestras raíces + externos verificados.
    # NO se llama start_all() — spawn perezoso, cada raíz arranca al primer dispatch.
    registry = McpRegistry(trunk_children(catalog, save_dir=save_dir, repo_root=repo_root))
    # Índice estático usando solo las raíces nativas (no requiere spawn).
    agg = TrunkAggregator(
        catalog=catalog,
        roots=native_roots(),  # índice estático, sin spawnear
        dispatcher=registry.dispatch,
    )
    from atlas.mcp.skills_store import SkillStore

    store = SkillStore(Path(repo_root) / "docs" / "skills")
    server = build_trunk_server(
        agg, name=name, skill_store=store, catalog=catalog, taxonomy=taxonomy
    )
    try:
        server.run()
    finally:
        registry.close_all()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("uso: python -m atlas.mcp.trunk_server <save_dir> <repo_root>")
    serve(save_dir=Path(sys.argv[1]), repo_root=Path(sys.argv[2]))
