"""Tests del builder de Resources del catálogo (puro, sin MCP)."""

from __future__ import annotations

import json

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.catalog_resources import (
    entry_id,
    item_detail,
    manifest_hash,
    manifest_json,
)


def _entry(
    name: str,
    *,
    kind: str = "mcp",
    sector: str = "programacion",
    subsector: str = "frontend",
    status: str = "verificado",
    mode: str = "connected",
) -> CatalogEntry:
    return CatalogEntry(
        name=name,
        sector=sector,
        sector_label=sector.title(),
        kind=kind,
        purpose=f"purpose of {name}",
        source=f"src/{name}",
        install=f"npx {name}",
        status=status,
        tags=["a", "b"],
        mode=mode,
        subsector=subsector,
    )


def test_entry_id_is_kind_slash_name() -> None:
    assert entry_id(_entry("foo", kind="skill")) == "skill/foo"


def test_manifest_has_four_axes_and_summary() -> None:
    entries = [
        _entry("foo", kind="mcp", status="verificado"),
        _entry("bar", kind="skill", status="instalado"),
    ]
    data = json.loads(manifest_json(entries))
    assert data["summary"]["total"] == 2
    assert data["summary"]["by_status"] == {"verificado": 1, "instalado": 1}
    assert data["summary"]["by_kind"] == {"mcp": 1, "skill": 1}
    item = next(i for i in data["items"] if i["name"] == "foo")
    # los 4 ejes pedidos por el usuario
    assert item["id"] == "mcp/foo"
    assert item["status"] == "verificado"
    assert item["kind"] == "mcp"
    assert item["domain"] == "programacion"
    assert item["subsector"] == "frontend"
    assert item["mode"] == "connected"
    # índice LIGERO: nada de prosa
    assert "purpose" not in item


def test_manifest_is_light_no_prose() -> None:
    data = json.loads(manifest_json([_entry("foo")]))
    assert set(data["items"][0].keys()) == {
        "id", "name", "status", "kind", "domain", "subsector", "mode",
    }


def test_fresh_changes_on_status_but_not_on_reorder() -> None:
    a, b = _entry("a"), _entry("b")
    h1 = manifest_hash([a, b])
    h2 = manifest_hash([b, a])  # reorden → mismo hash
    assert h1 == h2
    h3 = manifest_hash([_entry("a", status="candidato"), b])  # cambio de estado → distinto
    assert h3 != h1


def test_fresh_changes_on_mode() -> None:
    h1 = manifest_hash([_entry("a", mode="connected")])
    h2 = manifest_hash([_entry("a", mode="served")])
    assert h1 != h2


def test_empty_catalog_yields_empty_manifest() -> None:
    data = json.loads(manifest_json([]))
    assert data["summary"]["total"] == 0
    assert data["items"] == []


def test_item_detail_found_returns_full_entry() -> None:
    entries = [_entry("foo", kind="mcp"), _entry("bar", kind="skill")]
    detail = item_detail(entries, "mcp/foo")
    assert detail is not None
    d = json.loads(detail)
    assert d["id"] == "mcp/foo"
    assert d["purpose"] == "purpose of foo"
    assert d["install"] == "npx foo"
    assert d["tags"] == ["a", "b"]


def test_item_detail_missing_returns_none() -> None:
    assert item_detail([_entry("foo")], "mcp/does-not-exist") is None
