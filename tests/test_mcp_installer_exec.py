"""
Tests del instalador por `mode` (C pasos 5-6): plan de instalación + veto.

Solo lo `verificado` se planifica (wire-before-claim). Por mode:
  served    → noop (ya lo sirve el tronco; nada que bajar)
  connected → connect (comando de `install`, VETADO por SentinelGate pre-spawn)
  installed → place_skill (colocar en dir; solo si no se sirve)

Honesto: con 0 verificado, el plan está vacío (no instala nada).

Diseño: docs/design/mcp_sector_architecture_audit.md (paso 6, mapeo kind→destino).
"""

from __future__ import annotations


def _entry(name, *, kind, mode, status, install="", source=""):
    from atlas.mcp.catalog import CatalogEntry

    return CatalogEntry(
        name=name, sector="s", sector_label="S", kind=kind, purpose="", source=source,
        install=install, status=status, tags=["s"], mode=mode,
    )


def test_plan_only_verified_by_mode() -> None:
    from atlas.mcp.installer import plan_install

    entries = [
        _entry("served-skill", kind="skill", mode="served", status="verificado"),
        _entry("ext-mcp", kind="mcp", mode="connected", status="verificado", install="npx -y @foo/bar"),
        _entry("a-skill-dir", kind="skill", mode="installed", status="verificado", install="cp x y"),
        _entry("cand", kind="mcp", mode="connected", status="candidato", install="npx z"),
        _entry("already", kind="mcp", mode="connected", status="instalado", install="npx w"),
    ]
    plan = {a.name: a for a in plan_install(entries)}

    assert set(plan) == {"served-skill", "ext-mcp", "a-skill-dir"}  # solo verificado
    assert plan["served-skill"].action == "noop"
    assert plan["ext-mcp"].action == "connect"
    assert plan["ext-mcp"].command == ["npx", "-y", "@foo/bar"]
    assert plan["a-skill-dir"].action == "place_skill"


def test_empty_plan_when_nothing_verified() -> None:
    from atlas.mcp.installer import plan_install

    entries = [_entry("c", kind="mcp", mode="connected", status="candidato", install="npx z")]
    assert plan_install(entries) == []


def test_vet_blocks_command_with_shell_metachar() -> None:
    from atlas.mcp.installer import InstallAction, vet_action

    ok = InstallAction(name="ok", mode="connected", action="connect",
                       command=["npx", "-y", "@foo/bar"], note="")
    bad = InstallAction(name="bad", mode="connected", action="connect",
                        command=["sh", "-c", "a|b"], note="")
    assert vet_action(ok) is None              # comando limpio admitido
    assert vet_action(bad) is not None         # metacaracter de shell → veto


def test_real_catalog_plan_is_empty() -> None:
    """Honesto: el catálogo curado no tiene mcp `verificado` aún → plan vacío."""
    from pathlib import Path

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.installer import plan_install

    cat = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    # served verificado podría existir, pero connected/installed verificado no.
    actions = [a for a in plan_install(load_catalog(cat)) if a.action != "noop"]
    assert actions == []
