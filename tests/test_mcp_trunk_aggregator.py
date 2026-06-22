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
