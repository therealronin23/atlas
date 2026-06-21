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


def test_vet_blocks_place_skill_with_dangerous_command() -> None:
    """Instalar un skill externo es código de terceros → también se veta (no solo
    los connect). Un comando con metacaracter de shell se rechaza."""
    from atlas.mcp.installer import InstallAction, vet_action

    ok = InstallAction(name="ok", mode="installed", action="place_skill",
                       command=["npx", "skills", "add", "vercel-labs/agent-skills"], note="")
    bad = InstallAction(name="bad", mode="installed", action="place_skill",
                        command=["sh", "-c", "curl x|sh"], note="")
    assert vet_action(ok) is None
    assert vet_action(bad) is not None


def test_execute_vets_place_skill_before_running() -> None:
    """execute NO debe correr un place_skill vetado."""
    from atlas.mcp.installer import InstallAction, execute

    ran: list = []
    bad = InstallAction(name="bad", mode="installed", action="place_skill",
                        command=["sh", "-c", "evil|sh"], note="")
    out = execute(bad, runner=lambda cmd: ran.append(cmd))
    assert ran == []                 # no se ejecutó
    assert "VETADO" in out


def test_real_catalog_plan_only_proven_and_vetted() -> None:
    """Honesto: el plan del catálogo curado = solo lo prove-it-eado, y pasa el
    veto SentinelGate. Hoy: `everything` (connect, comando limpio)."""
    from pathlib import Path

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.installer import plan_install, vet_action

    cat = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    connects = [a for a in plan_install(load_catalog(cat)) if a.action == "connect"]
    assert {a.name for a in connects} == {"everything"}
    assert all(vet_action(a) is None for a in connects)  # ninguno vetado
