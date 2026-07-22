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


class TestPluginActivatedSkills:
    """ADR-073 A3.3 dejó documentado un gap real: los plugins activados
    (`<workspace>/plugins/active/<id>/skill/*.md`) no eran visibles a
    `SkillStore` — mecanismo completo, cero consumidor. `plugins_active_root`
    es opt-in (kw-only, default `None`): sin él, comportamiento IDÉNTICO al
    de siempre (los tests de arriba, sin tocar, lo prueban)."""

    def test_backward_compatible_without_plugins_root(self, tmp_path: Path) -> None:
        from atlas.mcp.skills_store import SkillStore

        (tmp_path / "core.md").write_text("# Core\n", encoding="utf-8")
        store = SkillStore(tmp_path)

        assert store.list_skills() == ["core"]

    def test_lists_plugin_skills_namespaced(self, tmp_path: Path) -> None:
        from atlas.mcp.skills_store import SkillStore

        active = tmp_path / "active"
        skill_dir = active / "demo-plugin" / "skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "demo-skill.md").write_text("# Plugin skill\n", encoding="utf-8")
        store = SkillStore(tmp_path / "core", plugins_active_root=active)

        names = store.list_skills()

        assert "plugin:demo-plugin/demo-skill" in names

    def test_get_returns_plugin_skill_content(self, tmp_path: Path) -> None:
        from atlas.mcp.skills_store import SkillStore

        active = tmp_path / "active"
        skill_dir = active / "demo-plugin" / "skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "demo-skill.md").write_text(
            "# Plugin skill\n\nContenido real.\n", encoding="utf-8"
        )
        store = SkillStore(tmp_path / "core", plugins_active_root=active)

        content = store.get("plugin:demo-plugin/demo-skill")

        assert "Contenido real." in content

    def test_get_follows_symlink_like_the_real_activator(self, tmp_path: Path) -> None:
        # PluginActivator NUNCA copia bytes: aplica por symlink. SkillStore
        # debe servir el contenido del destino, no rechazar el link.
        from atlas.mcp.skills_store import SkillStore

        real_source = tmp_path / "staging" / "demo.md"
        real_source.parent.mkdir(parents=True)
        real_source.write_text("# Via symlink\n", encoding="utf-8")
        active = tmp_path / "active"
        skill_dir = active / "demo-plugin" / "skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "demo-skill.md").symlink_to(real_source)
        store = SkillStore(tmp_path / "core", plugins_active_root=active)

        assert store.get("plugin:demo-plugin/demo-skill") == "# Via symlink\n"

    def test_get_missing_plugin_skill_raises(self, tmp_path: Path) -> None:
        import pytest

        from atlas.mcp.skills_store import SkillStore

        store = SkillStore(tmp_path / "core", plugins_active_root=tmp_path / "active")
        with pytest.raises(KeyError):
            store.get("plugin:nope/nope")

    def test_get_malformed_plugin_name_raises(self, tmp_path: Path) -> None:
        import pytest

        from atlas.mcp.skills_store import SkillStore

        store = SkillStore(tmp_path / "core", plugins_active_root=tmp_path / "active")
        with pytest.raises(KeyError):
            store.get("plugin:no-slash-here")

    def test_path_traversal_in_plugin_id_is_rejected(self, tmp_path: Path) -> None:
        import pytest

        from atlas.mcp.skills_store import SkillStore

        secret = tmp_path / "secret.txt"
        secret.write_text("no me leas", encoding="utf-8")
        active = tmp_path / "active"
        active.mkdir()
        store = SkillStore(tmp_path / "core", plugins_active_root=active)

        with pytest.raises(KeyError):
            store.get("plugin:../secret.txt/x")
        with pytest.raises(KeyError):
            store.get("plugin:x/../../secret.txt")

    def test_plugin_without_skill_contributions_contributes_nothing(
        self, tmp_path: Path
    ) -> None:
        from atlas.mcp.skills_store import SkillStore

        active = tmp_path / "active"
        (active / "no-skills-plugin" / "prompt").mkdir(parents=True)
        (active / "no-skills-plugin" / "prompt" / "p.md").write_text("x", encoding="utf-8")
        store = SkillStore(tmp_path / "core", plugins_active_root=active)

        assert store.list_skills() == []

    def test_missing_plugins_active_root_is_not_an_error(self, tmp_path: Path) -> None:
        from atlas.mcp.skills_store import SkillStore

        store = SkillStore(tmp_path / "core", plugins_active_root=tmp_path / "does-not-exist")

        assert store.list_skills() == []

    def test_core_and_plugin_skills_never_collide_by_name(self, tmp_path: Path) -> None:
        # Un plugin con contribution_id="atlas-coding-discipline" NO debe
        # sombrear (ni ser confundido con) el skill nativo del mismo nombre.
        from atlas.mcp.skills_store import SkillStore

        core = tmp_path / "core"
        core.mkdir()
        (core / "atlas-coding-discipline").with_suffix(".md").write_text(
            "# Nativo\n", encoding="utf-8"
        )
        active = tmp_path / "active"
        skill_dir = active / "demo-plugin" / "skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "atlas-coding-discipline.md").write_text("# Plugin\n", encoding="utf-8")
        store = SkillStore(core, plugins_active_root=active)

        assert store.get("atlas-coding-discipline") == "# Nativo\n"
        assert store.get("plugin:demo-plugin/atlas-coding-discipline") == "# Plugin\n"

    def test_end_to_end_with_real_plugin_activator(self, tmp_path: Path) -> None:
        # Integración real, no doble: activa un plugin de verdad con
        # PluginActivator y confirma que SkillStore lo sirve.
        import json

        from atlas.core.decider.autonomous_decider import AutonomousDecider
        from atlas.logging.merkle_logger import MerkleLogger
        from atlas.mcp.plugin_activator import PluginActivator
        from atlas.mcp.plugin_materializer import PluginMaterializer
        from atlas.mcp.plugin_receipt_broker import PluginReceiptBroker
        from atlas.mcp.skills_store import SkillStore

        source = tmp_path / "src" / "e2e-plugin"
        source.mkdir(parents=True)
        (source / "atlas-plugin.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "plugin_id": "e2e-plugin",
                    "display_name": "E2E plugin",
                    "version": "1.0.0",
                    "source": {
                        "origin": "local://test/e2e-plugin",
                        "revision": "fixture-1",
                        "license": "Apache-2.0",
                    },
                    "activation": "declarative",
                    "permissions": [],
                    "contributions": [
                        {"contribution_id": "e2e-skill", "kind": "skill", "path": "skills/e2e.md"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        (source / "skills").mkdir()
        (source / "skills" / "e2e.md").write_text(
            "# E2E skill\n\nServido de verdad tras activar, sin dobles.\n",
            encoding="utf-8",
        )
        materialized = PluginMaterializer(staging_root=tmp_path / "staging").materialize_local(
            source, expected_plugin_id="e2e-plugin"
        )
        merkle = MerkleLogger(tmp_path / "merkle")
        broker = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=AutonomousDecider()
        )
        receipt = broker.request(materialized)
        activator = PluginActivator(
            broker=broker,
            merkle=merkle,
            active_root=tmp_path / "active",
            store_dir=tmp_path / "activations",
            decider=AutonomousDecider(),
        )
        record = activator.activate(receipt.receipt_id)
        assert record.status == "activated"

        store = SkillStore(tmp_path / "core-skills", plugins_active_root=tmp_path / "active")

        assert "plugin:e2e-plugin/e2e-skill" in store.list_skills()
        assert "Servido de verdad" in store.get("plugin:e2e-plugin/e2e-skill")


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
