"""Tests de `PluginPromptStore` (t1-plugin-contribution-consumers, backlog.yaml).

`PluginManifest v1` (ADR-073) admite 4 tipos de contribución: skill, prompt, rule,
command. Hasta este ítem solo `skill` tenía consumidor real (`SkillStore` vía
`plugins_active_root`, ver `test_mcp_skills_store.py`). Este módulo cierra el hueco
para `prompt`: mismo patrón exacto de `SkillStore` (namespace `plugin:<plugin_id>/
<contribution_id>`, sigue symlinks porque `PluginActivator` aplica por symlink,
fuente única — nunca copia bytes), pero SIN raíz nativa (a diferencia de skill, no
hay prompts "core" bundleados hoy — solo los que aporte un plugin).

`rule` y `command` quedan sin consumidor propio, documentados como tal en
`docs/design/plugin_manifest_v1.md` (aplicados mecánicamente por PluginActivator,
nada los lee).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_list_prompts_empty_without_active_root(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    store = PluginPromptStore(tmp_path / "does-not-exist")

    assert store.list_prompts() == []


def test_lists_plugin_prompts_namespaced(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    active = tmp_path / "active"
    prompt_dir = active / "demo-plugin" / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "demo-prompt.md").write_text("# Plugin prompt\n", encoding="utf-8")
    store = PluginPromptStore(active)

    names = store.list_prompts()

    assert names == ["plugin:demo-plugin/demo-prompt"]


def test_get_returns_plugin_prompt_content(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    active = tmp_path / "active"
    prompt_dir = active / "demo-plugin" / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "demo-prompt.md").write_text(
        "# Plugin prompt\n\nContenido real.\n", encoding="utf-8"
    )
    store = PluginPromptStore(active)

    content = store.get("plugin:demo-plugin/demo-prompt")

    assert "Contenido real." in content


def test_get_follows_symlink_like_the_real_activator(tmp_path: Path) -> None:
    # PluginActivator NUNCA copia bytes: aplica por symlink. El store debe
    # servir el contenido del destino, no rechazar el link.
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    real_source = tmp_path / "staging" / "demo.md"
    real_source.parent.mkdir(parents=True)
    real_source.write_text("# Via symlink\n", encoding="utf-8")
    active = tmp_path / "active"
    prompt_dir = active / "demo-plugin" / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "demo-prompt.md").symlink_to(real_source)
    store = PluginPromptStore(active)

    assert store.get("plugin:demo-plugin/demo-prompt") == "# Via symlink\n"


def test_get_missing_plugin_prompt_raises(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    store = PluginPromptStore(tmp_path / "active")
    with pytest.raises(KeyError):
        store.get("plugin:nope/nope")


def test_get_without_plugin_prefix_raises(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    store = PluginPromptStore(tmp_path / "active")
    with pytest.raises(KeyError):
        store.get("bare-name")


def test_get_malformed_name_raises(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    store = PluginPromptStore(tmp_path / "active")
    with pytest.raises(KeyError):
        store.get("plugin:no-slash-here")


def test_path_traversal_in_plugin_id_is_rejected(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    secret = tmp_path / "secret.txt"
    secret.write_text("no me leas", encoding="utf-8")
    active = tmp_path / "active"
    active.mkdir()
    store = PluginPromptStore(active)

    with pytest.raises(KeyError):
        store.get("plugin:../secret.txt/x")
    with pytest.raises(KeyError):
        store.get("plugin:x/../../secret.txt")


def test_plugin_without_prompt_contributions_contributes_nothing(tmp_path: Path) -> None:
    from atlas.mcp.plugin_prompt_store import PluginPromptStore

    active = tmp_path / "active"
    (active / "no-prompts-plugin" / "skill").mkdir(parents=True)
    (active / "no-prompts-plugin" / "skill" / "s.md").write_text("x", encoding="utf-8")
    store = PluginPromptStore(active)

    assert store.list_prompts() == []


def test_end_to_end_with_real_plugin_activator(tmp_path: Path) -> None:
    # Integración real, no doble: activa un plugin de verdad con
    # PluginActivator (contribución kind="prompt") y confirma que
    # PluginPromptStore lo sirve.
    import json

    from atlas.core.decider.autonomous_decider import AutonomousDecider
    from atlas.logging.merkle_logger import MerkleLogger
    from atlas.mcp.plugin_activator import PluginActivator
    from atlas.mcp.plugin_materializer import PluginMaterializer
    from atlas.mcp.plugin_prompt_store import PluginPromptStore
    from atlas.mcp.plugin_receipt_broker import PluginReceiptBroker

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
                    {"contribution_id": "e2e-prompt", "kind": "prompt", "path": "prompts/e2e.md"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (source / "prompts").mkdir()
    (source / "prompts" / "e2e.md").write_text(
        "# E2E prompt\n\nServido de verdad tras activar, sin dobles.\n",
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

    store = PluginPromptStore(tmp_path / "active")

    assert "plugin:e2e-plugin/e2e-prompt" in store.list_prompts()
    assert "Servido de verdad" in store.get("plugin:e2e-plugin/e2e-prompt")


def test_trunk_registers_activated_plugin_prompt_as_mcp_prompt(tmp_path: Path) -> None:
    """Demuestra el cambio de comportamiento OBSERVABLE exigido por el criterio de
    aceptación: activar un plugin con una contribución `prompt` hace que un cliente
    MCP real (`server.list_prompts()`/`server.get_prompt()`) vea y pueda leer ese
    prompt — algo que antes de este ítem era imposible para CUALQUIER `prompt` de
    plugin (mecanismo sin consumidor, ver plugin_manifest_v1.md)."""
    import asyncio

    pytest.importorskip("mcp")

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.plugin_prompt_store import PluginPromptStore
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots
    from atlas.mcp.trunk_server import build_trunk_server

    active = tmp_path / "active"
    prompt_dir = active / "demo-plugin" / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "demo-prompt.md").write_text(
        "Instrucción real del plugin.", encoding="utf-8"
    )

    catalog = load_catalog(
        Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    )
    agg = TrunkAggregator(catalog=catalog, roots=native_roots(), dispatcher=lambda f, a: "x")
    prompt_store = PluginPromptStore(active)

    server = build_trunk_server(agg, plugin_prompt_store=prompt_store)

    names = {p.name for p in asyncio.run(server.list_prompts())}
    assert "plugin:demo-plugin/demo-prompt" in names

    result = asyncio.run(server.get_prompt("plugin:demo-plugin/demo-prompt"))
    joined = "\n".join(
        m.content.text for m in result.messages if hasattr(m.content, "text")
    )
    assert "Instrucción real del plugin." in joined


def test_trunk_without_plugin_prompt_store_registers_no_plugin_prompts(tmp_path: Path) -> None:
    """Sin `plugin_prompt_store` (default `None`) el comportamiento es IDÉNTICO al
    de siempre — igual que `SkillStore.plugins_active_root` opcional."""
    import asyncio

    pytest.importorskip("mcp")

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots
    from atlas.mcp.trunk_server import build_trunk_server

    catalog = load_catalog(
        Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    )
    agg = TrunkAggregator(catalog=catalog, roots=native_roots(), dispatcher=lambda f, a: "x")

    server = build_trunk_server(agg)

    names = {p.name for p in asyncio.run(server.list_prompts())}
    assert names == set()
