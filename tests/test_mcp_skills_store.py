"""
Tests del SkillStore (C paso 3): skills SERVIDOS por el MCP, sin descarga.

Un skill = markdown servido como contenido del MCP (tool `get_skill` + resource +
prompt donde haya soporte). El modelo accede "de una"; nada se instala en un dir.
Fuente única (anti-deriva): el fichero markdown ES la fuente; no se copia.

Diseño: docs/design/mcp_sector_architecture_audit.md (mecanismo de skills).
"""

from __future__ import annotations

from pathlib import Path


def test_lists_bundled_skills_from_repo() -> None:
    from atlas.mcp.skills_store import SkillStore

    store = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills")
    names = store.list_skills()
    assert "atlas-coding-discipline" in names  # 1 skill real bundleado


def test_get_returns_markdown_content() -> None:
    from atlas.mcp.skills_store import SkillStore

    store = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills")
    content = store.get("atlas-coding-discipline")
    assert content.strip()
    assert "wire-before-claim" in content  # contenido real, nuestro


def test_get_missing_raises(tmp_path: Path) -> None:
    import pytest

    from atlas.mcp.skills_store import SkillStore

    store = SkillStore(tmp_path)
    with pytest.raises(KeyError):
        store.get("nope")


def test_trunk_serves_get_skill_tool(tmp_path: Path) -> None:
    import asyncio

    import pytest

    pytest.importorskip("mcp")

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.skills_store import SkillStore
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots
    from atlas.mcp.trunk_server import build_trunk_server

    catalog = load_catalog(
        Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    )
    agg = TrunkAggregator(catalog=catalog, roots=native_roots(), dispatcher=lambda f, a: "x")
    store = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills")
    server = build_trunk_server(agg, skill_store=store)

    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"get_skill", "list_skills"} <= names


def test_trunk_3level_nav_and_find() -> None:
    import asyncio
    from pathlib import Path

    import pytest

    pytest.importorskip("mcp")

    from atlas.mcp.catalog import load_catalog, load_taxonomy
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots
    from atlas.mcp.trunk_server import build_trunk_server

    cat = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    catalog, tax = load_catalog(cat), load_taxonomy(cat)
    agg = TrunkAggregator(catalog=catalog, roots=native_roots(), dispatcher=lambda f, a: "x")
    server = build_trunk_server(agg, catalog=catalog, taxonomy=tax)
    names = {t.name for t in asyncio.run(server.list_tools())}
    # navegación 3 niveles + buscador + navegación POR LÍNEA (kind)
    assert {"trunk_sectors", "trunk_subsectors", "trunk_tools", "trunk_find",
            "trunk_kinds", "trunk_catalog"} <= names
