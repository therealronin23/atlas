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

    from atlas.core.self_maintenance.backlog import BacklogItem
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
            cmd=[exe, "-m", root.module, *([arg_for[root.arg_kind]] if root.arg_kind else [])],
            # recall/lookup/audit/graph son de lectura; el resto mutan (HITL).
            read_only_tools=[t for t in root.tools if t.startswith(("recall", "wikipedia_lookup", "worldbank_lookup", "sanitation", "graph_"))],
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
                read_only_tools=list(e.read_only_tools),  # ADR-035 dec.5: resto = mutate/HITL
            ))
    return out


def trunk_health_snapshot(
    catalog: list["CatalogEntry"],
    configs: list[McpServerConfig],
) -> dict[str, Any]:
    """Diagnóstico barato del trunk, sin spawnear servidores ni ejecutar terceros."""
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for entry in catalog:
        by_status[entry.status] = by_status.get(entry.status, 0) + 1
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1

    configured: list[dict[str, Any]] = []
    missing_env_total: dict[str, list[str]] = {}
    for cfg in configs:
        _env, missing = cfg.resolve_env()
        if missing:
            missing_env_total[cfg.name] = missing
        configured.append(
            {
                "name": cfg.name,
                "enabled": cfg.enabled and not missing,
                "cmd0": cfg.cmd[0] if cfg.cmd else "",
                "read_only_tools": list(cfg.read_only_tools),
                "missing_env": missing,
                "timeout_seconds": cfg.timeout_seconds,
            }
        )

    trial_ready: list[dict[str, str]] = []
    for entry in catalog:
        if entry.kind != "mcp" or entry.status != "candidato":
            continue
        if not entry.install and not entry.source:
            continue
        trial_ready.append(
            {
                "name": entry.name,
                "sector": entry.sector,
                "subsector": entry.subsector,
                "source": entry.source,
                "install": entry.install,
                "trust": entry.trust,
            }
        )
    trial_ready.sort(
        key=lambda r: (
            0 if r["trust"] == "research-2026" else 1,
            r["sector"],
            r["name"].lower(),
        )
    )

    return {
        "status": "ok" if not missing_env_total else "degraded",
        "catalog": {
            "total": len(catalog),
            "by_status": by_status,
            "by_kind": by_kind,
        },
        "configured_servers": configured,
        "missing_env_by_server": missing_env_total,
        "trial_ready_candidates": trial_ready[:20],
        "policy": "health does not spawn or install; candidates require trial + review + explicit consent",
    }


def build_trunk_server(
    agg: TrunkAggregator,
    *,
    name: str = "atlas-trunk",
    skill_store: "SkillStore | None" = None,
    catalog: "list[CatalogEntry] | None" = None,
    taxonomy: dict[str, Any] | None = None,
    lesson_store: Any | None = None,
    backlog_items: "list[BacklogItem] | None" = None,
    memory_count: int | None = None,
    health_configs: list[McpServerConfig] | None = None,
) -> "FastMCP":
    """Servidor FastMCP que expone la fachada meta lazy del tronco (navegación de 3
    niveles + buscador). Con `skill_store` sirve skills; con `catalog`+`taxonomy`
    expone `trunk_subsectors` y `trunk_find` (salto directo, sin manual). Con
    `catalog`+`lesson_store`+`backlog_items`+`memory_count` expone SP-A
    (`workbench://manifest`, la mesa de trabajo compartida — ver
    `workbench_resources.py`)."""
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

    @server.tool()
    def trunk_invoke_readonly(tool: str, args: dict[str, Any] | None = None) -> Any:
        """Ejecuta una tool de SOLO LECTURA (declarada read_only en el catálogo de su
        raíz). Fail-closed: rechaza cualquier tool no declarada — para mutaciones usa
        trunk_invoke (que pasa por HITL en el host)."""
        return agg.invoke_readonly(tool, args or {})

    if taxonomy is not None:
        @server.tool()
        def trunk_subsectors(sector: str) -> list[dict[str, Any]]:
            """Subsectores de un sector (nivel 2): el mapa fino, sin manual."""
            sub = (taxonomy.get(sector) or {}).get("subsectors", {})
            return [{"id": sid, "label": s["label"]} for sid, s in sub.items()]

    if catalog is not None:
        from atlas.mcp.catalog import by_kind as _by_kind
        from atlas.mcp.catalog_resources import item_detail as _item_detail
        from atlas.mcp.catalog_resources import manifest_json as _manifest_json

        @server.resource("catalog://manifest", mime_type="application/json")
        def catalog_manifest() -> str:
            """Índice del catálogo (JSON): summary + `fresh` + items con sus 4 ejes
            (status/kind/domain+subsector/mode). Léelo UNA vez en vez de navegar por
            tool-calls. El detalle de un item va por `catalog://item/{kind}/{name}`."""
            return _manifest_json(catalog)

        @server.resource("catalog://item/{kind}/{name}", mime_type="application/json")
        def catalog_item(kind: str, name: str) -> str:
            """Detalle COMPLETO de un item del catálogo (todos sus campos)."""
            detail = _item_detail(catalog, f"{kind}/{name}")
            if detail is None:
                raise ValueError(f"catalog item not found: {kind}/{name}")
            return detail

        @server.tool()
        def trunk_kinds() -> dict[str, int]:
            """Las LÍNEAS del catálogo (kind→cuántos): mcp, skill, api, tool, prompt,
            hook, subagent, plugin, rule, workflow. Cada línea es un 'StormMCP'."""
            return _by_kind(catalog)

        @server.tool()
        def trunk_health() -> dict[str, Any]:
            """Diagnóstico sin efectos: catálogo, servers configurados, read-only y
            secretos faltantes por nombre. No spawnea ni instala terceros."""
            return trunk_health_snapshot(catalog, health_configs or [])

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
        from atlas.mcp.catalog import recommended_stack as _recommended_stack
        from atlas.mcp.trunk_prepare import prepare_task_context as _prepare_task_context

        @server.tool()
        def trunk_find(query: str) -> list[dict[str, Any]]:
            """Salto directo: busca por nombre/alias (p.ej. 'seguridad', 'figma') y
            devuelve el camino sector/subsector, madurez-first. No hace falta navegar."""
            return _find(catalog, taxonomy, query)

        @server.tool()
        def trunk_recommend_stack(goal: str, limit: int = 8) -> dict[str, Any]:
            """Shortlist 2026 por objetivo: instalado/verificado primero; candidatos
            solo como descubrimiento. No instala ni ejecuta terceros."""
            return _recommended_stack(catalog, taxonomy, goal, limit=limit)

        @server.tool()
        def trunk_prepare(
            goal: str,
            constraints: dict[str, Any] | None = None,
            limit: int = 8,
        ) -> dict[str, Any]:
            """Preflight compacto por tarea: recomienda tools/skills/resources ya
            conocidos, marca candidatos como NO conectados, e incorpora uso real.
            No spawnea, instala, descarga ni ejecuta terceros."""
            external_counts: dict[str, int] = {}
            usage_counter = getattr(agg, "_usage_counter", None)
            if usage_counter is not None:
                try:
                    external_counts = usage_counter.external_counts()
                except Exception:  # noqa: BLE001 — métrica, nunca bloquea preflight
                    external_counts = {}
            return _prepare_task_context(
                catalog,
                taxonomy,
                goal,
                limit=limit,
                external_counts=external_counts,
                workbench_available=(
                    lesson_store is not None
                    and backlog_items is not None
                    and memory_count is not None
                ),
                constraints=constraints,
            )

    if skill_store is not None:
        @server.tool()
        def list_skills() -> list[str]:
            """Skills servidos por el tronco (sin descarga)."""
            return skill_store.list_skills()

        @server.tool()
        def get_skill(name: str) -> str:
            """Devuelve el contenido de un skill (markdown). Acceso 'de una', sin instalar."""
            return skill_store.get(name)

        # Además: cada skill como PROMPT MCP nativo (descubrible por el cliente —
        # slash-commands/autocompletado — sin un tool-call). Aditivo a get_skill.
        # El cuerpo se carga PEREZOSAMENTE al pedir el prompt (registro = solo nombres).
        from mcp.server.fastmcp.prompts.base import Prompt

        def _make_skill_prompt(skill_name: str) -> Prompt:
            def _skill_body() -> str:
                return skill_store.get(skill_name)

            return Prompt.from_function(
                _skill_body,
                name=skill_name,
                description=f"Atlas skill servido por el tronco: {skill_name}",
            )

        for _sname in skill_store.list_skills():
            server.add_prompt(_make_skill_prompt(_sname))

    if (
        catalog is not None
        and lesson_store is not None
        and backlog_items is not None
        and memory_count is not None
    ):
        from atlas.mcp.workbench_resources import workbench_manifest_json as _workbench_manifest_json

        @server.resource("workbench://manifest", mime_type="application/json")
        def workbench_manifest() -> str:
            """SP-A: la mesa de trabajo compartida. Un único Resource que agrega
            catálogo+lecciones+backlog+memoria — léelo UNA vez al planificar en vez
            de conocer cada subsistema por separado o hacer N tool-calls."""
            return _workbench_manifest_json(catalog, lesson_store, backlog_items, memory_count)

    # Cierre de primitivos MCP (audit): Completion + Logging/Progress (consumidor real).
    from atlas.mcp.trunk_capabilities import (
        register_discovery_capabilities,
        register_subscription_capabilities,
        register_workflow_capabilities,
    )

    register_discovery_capabilities(server, catalog=catalog, skill_store=skill_store)
    # Client-features (Elicitation/Sampling/Roots): capacidad lista; consumidor = SP-E.
    register_workflow_capabilities(server)
    if catalog is not None:
        register_subscription_capabilities(server)

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
    children = trunk_children(catalog, save_dir=save_dir, repo_root=repo_root)
    registry = McpRegistry(children)

    def _refresh(tool: str) -> dict[str, list[str]]:
        # Routing perezoso de externos: spawnea hijos uno a uno (ensure_started es
        # idempotente) hasta que el tool buscado aparezca en el registry.
        for cfg in children:
            registry.ensure_started(cfg.name)
            found = servers_from_registry(registry)
            if any(tool in tools for tools in found.values()):
                return found
        return servers_from_registry(registry)

    from atlas.mcp.tool_usage import ToolUsageCounter

    # Índice estático usando solo las raíces nativas (no requiere spawn); los
    # externos entran vía _refresh al primer invoke de una de sus tools.
    agg = TrunkAggregator(
        catalog=catalog,
        roots=native_roots(),  # índice estático, sin spawnear
        dispatcher=registry.dispatch,
        refresh=_refresh,
        is_read_only=registry.is_read_only,
        # Antes ausente por completo: ninguna métrica de uso real por tool.
        usage_counter=ToolUsageCounter(Path(save_dir) / "tool_usage.json"),
    )
    from atlas.mcp.skills_store import SkillStore

    store = SkillStore(Path(repo_root) / "docs" / "skills")

    # SP-A: mesa de trabajo compartida — fuentes reales para workbench://manifest.
    # Fail-soft por diseño: si algo falta (backlog.yaml ausente, DB de memoria
    # aún no creada), el tronco arranca igual sin ese resource, nunca rompe el
    # resto del servidor por una pieza opcional.
    lesson_store_obj: Any | None = None
    backlog_items_list: list[Any] | None = None
    memory_count_val: int | None = None
    try:
        from atlas.core.lesson_store import LessonStore

        # 2026-07-03: unificado a <repo_root>/workspace/lessons — la MISMA
        # convención que AtlasCoder/ToolCoder (donde YA viven lecciones reales
        # generadas por el propio motor de codificación). Antes apuntaba a
        # `save_dir/lessons` (p.ej. ~/atlas-mcp/lessons) — una ruta vacía
        # desconectada de donde el resto de Atlas escribe lecciones de verdad
        # (hallazgo real, verificado en vivo).
        lesson_store_obj = LessonStore(Path(repo_root) / "workspace" / "lessons")
    except Exception:  # noqa: BLE001 — SP-A es aditivo, nunca bloquea el arranque
        lesson_store_obj = None
    try:
        from atlas.core.self_maintenance.backlog import load_backlog

        backlog_path = Path(repo_root) / "docs" / "backlog.yaml"
        if backlog_path.is_file():
            backlog_items_list = load_backlog(backlog_path)
    except Exception:  # noqa: BLE001
        backlog_items_list = None
    try:
        memory_db = Path(save_dir) / "memory.db"
        if memory_db.is_file():
            import sqlite3

            conn = sqlite3.connect(str(memory_db))
            try:
                memory_count_val = int(
                    conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                )
            finally:
                conn.close()
        else:
            memory_count_val = 0
    except Exception:  # noqa: BLE001
        memory_count_val = None

    server = build_trunk_server(
        agg, name=name, skill_store=store, catalog=catalog, taxonomy=taxonomy,
        lesson_store=lesson_store_obj, backlog_items=backlog_items_list,
        memory_count=memory_count_val, health_configs=children,
    )
    try:
        server.run()
    finally:
        registry.close_all()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("uso: python -m atlas.mcp.trunk_server <save_dir> <repo_root>")
    serve(save_dir=Path(sys.argv[1]), repo_root=Path(sys.argv[2]))
