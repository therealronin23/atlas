"""
Tests del TRONCO-AGREGADOR (línea B): un MCP único que frontea las raíces,
CLASIFICADAS por sector, con descubrimiento LAZY/jerárquico (anti-kitchen-sink) —
el concepto asimilado de 1mcp/MarimerLLC/metamcp sobre NUESTRA base.

Capa NEUTRA (`TrunkAggregator`): Python puro. El dispatcher (que reenvía a la raíz
real) se INYECTA → testeable sin spawnear procesos; en producción lo provee
McpRegistry (Merkle + SentinelGate, nuestro diferencial).

Lazy: el cliente ve primero `sectors()` (índice pequeño), luego baja a
`tools_in(sector)` (drill-down). No ve las N tools de golpe.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CATALOG = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"


def _agg(dispatcher=None):
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots

    return TrunkAggregator(
        catalog=load_catalog(_CATALOG),
        roots=native_roots(),
        dispatcher=dispatcher or (lambda full_name, args: f"called:{full_name}"),
    )


# ---------------------------------------------------------------------------
# Índice lazy nivel 1: sectores (pequeño, sin schemas)
# ---------------------------------------------------------------------------


def test_sectors_groups_live_roots_by_catalog_sector() -> None:
    sectors = {s["sector"]: s for s in _agg().sectors()}
    # Las raíces vivas se agrupan por su sector (dominio) del catálogo v3.
    assert "infraestructura" in sectors      # atlas-operating vive aquí (operación)
    assert "conocimiento-memoria" in sectors  # atlas-memory + atlas-knowledge
    # infraestructura solo tiene atlas-operating (1 tool: sanitation_audit)
    assert sectors["infraestructura"]["tool_count"] == 1
    # cada sector trae label + cuenta, NO los schemas (lazy)
    assert sectors["infraestructura"]["label"]
    assert "tools" not in sectors["infraestructura"]


# ---------------------------------------------------------------------------
# Índice lazy nivel 2: drill-down a un sector
# ---------------------------------------------------------------------------


def test_tools_in_sector_returns_tools_with_root_and_purpose() -> None:
    tools = _agg().tools_in("infraestructura")
    names = {t["name"] for t in tools}
    assert "sanitation_audit" in names
    san = next(t for t in tools if t["name"] == "sanitation_audit")
    assert san["root"] == "atlas-operating"
    assert san["purpose"]  # purpose del catálogo, para guiar el routing


def test_tools_in_unknown_sector_is_empty() -> None:
    assert _agg().tools_in("no-such-sector") == []


# ---------------------------------------------------------------------------
# Dispatch: enruta a la raíz correcta vía namespacing mcp__<root>__<tool>
# ---------------------------------------------------------------------------


def test_invoke_routes_to_owning_root() -> None:
    seen: list[tuple[str, dict]] = []
    agg = _agg(dispatcher=lambda full_name, args: seen.append((full_name, args)) or "ok")
    out = agg.invoke("recall", {"query": "x"})
    assert out == "ok"
    assert seen == [("mcp__atlas-memory__recall", {"query": "x"})]


def test_invoke_unknown_tool_raises() -> None:
    with pytest.raises(KeyError):
        _agg().invoke("nope", {})


class _FakeUsageCounter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, tool_name: str) -> None:
        self.calls.append(tool_name)


def test_invoke_records_usage_when_counter_injected() -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots

    counter = _FakeUsageCounter()
    agg = TrunkAggregator(
        catalog=load_catalog(_CATALOG),
        roots=native_roots(),
        dispatcher=lambda full_name, args: "ok",
        usage_counter=counter,
    )
    agg.invoke("recall", {"query": "x"})
    assert counter.calls == ["mcp__atlas-memory__recall"]


def test_invoke_usage_counter_failure_does_not_block_dispatch() -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots

    class _BrokenCounter:
        def record(self, tool_name: str) -> None:
            raise RuntimeError("boom")

    agg = TrunkAggregator(
        catalog=load_catalog(_CATALOG),
        roots=native_roots(),
        dispatcher=lambda full_name, args: "ok",
        usage_counter=_BrokenCounter(),
    )
    assert agg.invoke("recall", {"query": "x"}) == "ok"


# ---------------------------------------------------------------------------
# Shell FastMCP del tronco: superficie PEQUEÑA (3 tools meta), no las N raíz
# ---------------------------------------------------------------------------


def test_build_trunk_server_exposes_small_meta_surface() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.trunk_server import build_trunk_server

    server = build_trunk_server(_agg())
    names = {t.name for t in asyncio.run(server.list_tools())}
    # Anti-kitchen-sink: el cliente ve la fachada meta, no las 8 tools de raíz.
    assert {"trunk_sectors", "trunk_tools", "trunk_invoke"} <= names
    assert "recall" not in names


# ---------------------------------------------------------------------------
# Cableado real: configs de McpRegistry para las 3 raíces vivas
# ---------------------------------------------------------------------------


def test_root_configs_map_each_root_to_its_launch_command(tmp_path: Path) -> None:
    from atlas.mcp.trunk_server import root_configs

    cfgs = {c.name: c for c in root_configs(
        save_dir=tmp_path / "save", repo_root=Path("/repo"), python="/py"
    )}
    assert set(cfgs) == {"atlas-memory", "atlas-operating", "atlas-knowledge"}

    mem = cfgs["atlas-memory"]
    assert mem.cmd[0] == "/py"
    assert "atlas.mcp.memory_server" in mem.cmd
    assert str(tmp_path / "save" / "memory.db") in mem.cmd
    # operating recibe el repo; knowledge recibe el base (kb)
    assert "/repo" in cfgs["atlas-operating"].cmd
    assert str(tmp_path / "save" / "kb") in cfgs["atlas-knowledge"].cmd


# ---------------------------------------------------------------------------
# Paso 2: tronco DIRIGIDO POR CATÁLOGO — hijos derivados del catálogo
# ---------------------------------------------------------------------------

_CHILDREN_CATALOG = """
sectors:
  memory-knowledge:
    label: Memoria
    entries:
      - {name: atlas-memory, kind: mcp, source: atlas.mcp.memory_server, status: instalado}
      - {name: ctx7, kind: mcp, install: "npx -y @upstash/context7-mcp", status: verificado}
      - {name: future-thing, kind: mcp, install: "npx foo", status: candidato}
      - {name: some-skill, kind: skill, status: instalado}
  operating:
    label: Operativa
    entries:
      - {name: atlas-operating, kind: mcp, source: atlas.mcp.operating_server, status: instalado}
"""


def test_trunk_children_derived_from_catalog(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import trunk_children

    cat = tmp_path / "c.yaml"
    cat.write_text(_CHILDREN_CATALOG, encoding="utf-8")
    children = {c.name: c for c in trunk_children(
        load_catalog(cat), save_dir=tmp_path / "save", repo_root=Path("/repo"), python="/py"
    )}

    # Conectables = mode connected (mcp) + status instalado/verificado.
    # Excluidos: candidato (future-thing) y skill (mode served, no se conecta).
    assert set(children) == {"atlas-memory", "ctx7", "atlas-operating"}

    # Nuestra raíz resuelve su comando con path arg (db); el externo usa su install.
    assert "atlas.mcp.memory_server" in children["atlas-memory"].cmd
    assert str(tmp_path / "save" / "memory.db") in children["atlas-memory"].cmd
    assert children["ctx7"].cmd == ["npx", "-y", "@upstash/context7-mcp"]


def test_trunk_children_pass_read_only_tools_from_catalog(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import trunk_children

    cat = tmp_path / "c.yaml"
    cat.write_text("""
sectors:
  programacion:
    label: Programación
    entries:
      - {name: playwright, kind: mcp, install: "npx -y @playwright/mcp@latest", status: verificado, read_only_tools: [browser_snapshot, browser_console_messages]}
""", encoding="utf-8")
    ch = {c.name: c for c in trunk_children(
        load_catalog(cat), save_dir=tmp_path, repo_root=Path("/repo"), python="/py")}
    # ADR-035 dec.5: lo declarado read_only pasa directo; el resto sigue mutate/HITL.
    assert ch["playwright"].read_only_tools == ["browser_snapshot", "browser_console_messages"]


def test_trunk_children_pass_env_passthrough_from_catalog(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import trunk_children

    cat = tmp_path / "c.yaml"
    cat.write_text("""
sectors:
  productividad:
    label: Productividad
    entries:
      - {name: gworkspace, kind: mcp, install: "uvx workspace-mcp", env_passthrough: [GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET], status: verificado}
""", encoding="utf-8")
    ch = {c.name: c for c in trunk_children(
        load_catalog(cat), save_dir=tmp_path, repo_root=Path("/repo"), python="/py")}
    # el secreto NO va en cmd; va como nombres de env vars a copiar del entorno.
    assert ch["gworkspace"].env_passthrough == ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
    assert "GOOGLE_OAUTH_CLIENT_SECRET" not in " ".join(ch["gworkspace"].cmd)


# ---------------------------------------------------------------------------
# El agregador indexa lo realmente CONECTADO (incl. externos), no solo native_roots
# ---------------------------------------------------------------------------

_EXT_CATALOG = """
sectors:
  commodity-infra:
    label: Commodity
    entries:
      - {name: everything, kind: mcp, purpose: "server de referencia", status: verificado}
  memory-knowledge:
    label: Memoria
    entries:
      - {name: atlas-memory, kind: mcp, source: atlas.mcp.memory_server, status: instalado}
"""


def test_aggregator_indexes_external_server_by_catalog_sector(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator

    cat = tmp_path / "c.yaml"
    cat.write_text(_EXT_CATALOG, encoding="utf-8")
    # servers = lo realmente conectado (server → tools), incluido el externo.
    servers = {"everything": ["echo", "get-sum"], "atlas-memory": ["recall"]}
    agg = TrunkAggregator(
        catalog=load_catalog(cat), servers=servers,
        dispatcher=lambda f, a: f,
    )
    sectors = {s["sector"]: s for s in agg.sectors()}
    assert "commodity-infra" in sectors  # el externo aparece en su sector
    assert {t["name"] for t in agg.tools_in("commodity-infra")} == {"echo", "get-sum"}
    # y enruta al externo
    assert agg.invoke("echo", {"m": "hi"}) == "mcp__everything__echo"


def test_invoke_unknown_tool_calls_refresh_and_retries(tmp_path: Path) -> None:
    """Routing perezoso: un tool de un MCP externo (no visible al construir el
    índice) se resuelve vía `refresh` (que spawnea al dueño) y se enruta."""
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator

    cat = tmp_path / "c.yaml"
    cat.write_text(_EXT_CATALOG, encoding="utf-8")
    calls: list[str] = []

    def refresh(tool: str) -> dict[str, list[str]]:
        calls.append(tool)
        return {"everything": ["echo", "get-sum"]}

    agg = TrunkAggregator(
        catalog=load_catalog(cat), servers={"atlas-memory": ["recall"]},
        dispatcher=lambda f, a: f, refresh=refresh,
    )
    assert agg.invoke("echo", {"m": "hi"}) == "mcp__everything__echo"
    assert calls == ["echo"]
    # segundo invoke: ya indexado, sin re-refresh
    assert agg.invoke("echo", {}) == "mcp__everything__echo"
    assert calls == ["echo"]
    # y sigue fallando limpio para lo realmente desconocido
    with pytest.raises(KeyError):
        agg.invoke("nope", {})


def test_invoke_readonly_dispatches_only_declared_read_only(tmp_path: Path) -> None:
    """ADR-035 dec.5 anidado: `invoke_readonly` solo despacha tools que el
    registry marca de lectura; todo lo demás se rechaza (fail-closed)."""
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator

    cat = tmp_path / "c.yaml"
    cat.write_text(_EXT_CATALOG, encoding="utf-8")
    agg = TrunkAggregator(
        catalog=load_catalog(cat), servers={"everything": ["echo", "get-sum"]},
        dispatcher=lambda f, a: f,
        is_read_only=lambda full: full == "mcp__everything__echo",
    )
    assert agg.invoke_readonly("echo", {}) == "mcp__everything__echo"
    with pytest.raises(PermissionError):
        agg.invoke_readonly("get-sum", {})


def test_invoke_readonly_fails_closed_without_predicate(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator

    cat = tmp_path / "c.yaml"
    cat.write_text(_EXT_CATALOG, encoding="utf-8")
    agg = TrunkAggregator(
        catalog=load_catalog(cat), servers={"everything": ["echo"]},
        dispatcher=lambda f, a: f,
    )
    with pytest.raises(PermissionError):
        agg.invoke_readonly("echo", {})


def test_servers_from_registry_parses_tool_specs() -> None:
    from atlas.mcp.trunk_server import servers_from_registry

    class _Reg:
        def tool_specs(self):
            return [
                {"function": {"name": "mcp__everything__echo"}},
                {"function": {"name": "mcp__everything__get-sum"}},
                {"function": {"name": "mcp__atlas-memory__recall"}},
            ]

    servers = servers_from_registry(_Reg())
    assert servers["everything"] == ["echo", "get-sum"]
    assert servers["atlas-memory"] == ["recall"]


def test_build_trunk_server_exposes_catalog_resources() -> None:
    pytest.importorskip("mcp")
    import asyncio
    import json

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import build_trunk_server

    catalog = load_catalog(_CATALOG)
    server = build_trunk_server(_agg(), catalog=catalog)

    # El índice está registrado como resource.
    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "catalog://manifest" in resources

    # Y se lee como JSON parseable con los 4 ejes + summary + fresh.
    manifest = list(asyncio.run(server.read_resource("catalog://manifest")))[0].content
    data = json.loads(manifest)
    assert data["summary"]["total"] == len(catalog)
    assert isinstance(data["fresh"], str) and data["fresh"]
    assert set(data["items"][0].keys()) == {
        "id", "name", "status", "kind", "domain", "subsector", "mode",
    }

    # El detalle por template devuelve el item completo.
    e = next(x for x in catalog if "/" not in x.name and " " not in x.name)
    uri = f"catalog://item/{e.kind}/{e.name}"
    detail = list(asyncio.run(server.read_resource(uri)))[0].content
    dd = json.loads(detail)
    assert dd["name"] == e.name and dd["kind"] == e.kind
    assert dd["purpose"] == e.purpose


def test_build_trunk_server_exposes_workbench_manifest(tmp_path: Path) -> None:
    """SP-A: workbench://manifest agrega catálogo+lecciones+backlog+memoria en
    un único Resource, con fuentes REALES (no mocks vacíos)."""
    pytest.importorskip("mcp")
    import asyncio
    import json

    from atlas.core.lesson_store import LessonStore
    from atlas.core.self_maintenance.backlog import BacklogItem
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import build_trunk_server

    catalog = load_catalog(_CATALOG)
    lesson_store = LessonStore(tmp_path / "lessons")
    backlog_items = [
        BacklogItem(
            id="x-1", title="Item pendiente", why="porque sí", targets=(),
            acceptance="tests verdes", priority=1, status="pending",
        ),
        BacklogItem(
            id="x-2", title="Item hecho", why="ya cerrado", targets=(),
            acceptance="tests verdes", priority=2, status="done",
        ),
    ]
    server = build_trunk_server(
        _agg(), catalog=catalog, lesson_store=lesson_store,
        backlog_items=backlog_items, memory_count=7,
    )

    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "workbench://manifest" in resources

    manifest = list(asyncio.run(server.read_resource("workbench://manifest")))[0].content
    data = json.loads(manifest)
    assert data["summary"]["catalog"]["total"] == len(catalog)
    assert data["summary"]["lessons"] == lesson_store.stats()
    assert data["summary"]["backlog"] == {"total": 2, "by_status": {"pending": 1, "done": 1}}
    assert data["summary"]["memory"] == {"count": 7}
    assert isinstance(data["fresh"], str) and len(data["fresh"]) == 16
    assert data["backlog_top_pending"] == [
        {"id": "x-1", "title": "Item pendiente", "priority": 1},
    ]


def test_build_trunk_server_omits_workbench_manifest_without_all_sources() -> None:
    """Aditivo/opcional: sin las 4 fuentes, el resource simplemente no se
    registra — nunca rompe el arranque del resto del tronco."""
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_server import build_trunk_server

    catalog = load_catalog(_CATALOG)
    server = build_trunk_server(_agg(), catalog=catalog)  # sin lesson_store/backlog/memory

    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "workbench://manifest" not in resources
    assert "catalog://manifest" in resources  # el resto sigue intacto


def test_build_trunk_server_exposes_skills_as_prompts() -> None:
    pytest.importorskip("mcp")
    import asyncio
    from pathlib import Path

    from atlas.mcp.skills_store import SkillStore
    from atlas.mcp.trunk_server import build_trunk_server

    store = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills")
    server = build_trunk_server(_agg(), skill_store=store)

    skills = set(store.list_skills())
    assert skills  # sanity: hay skills servidos

    # Cada skill aparece como PROMPT nativo (no solo como tool get_skill).
    prompts = {p.name for p in asyncio.run(server.list_prompts())}
    assert skills <= prompts

    # Y el cuerpo del prompt coincide con el contenido del skill (carga perezosa).
    sample = sorted(skills)[0]
    got = asyncio.run(server.get_prompt(sample, {}))
    body = got.messages[0].content.text
    assert body == store.get(sample)
