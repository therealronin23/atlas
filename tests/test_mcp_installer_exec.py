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


def test_execute_never_runs_clean_third_party_command_without_future_admission_executor() -> None:
    """A2 retira el atajo: argv limpio no acredita bytes ni aprobación humana."""
    from atlas.mcp.installer import InstallAction, execute

    ran: list[list[str]] = []
    clean = InstallAction(
        name="remote-plugin",
        mode="installed",
        action="place_skill",
        command=["npx", "-y", "remote-plugin"],
        note="",
    )

    out = execute(clean, runner=ran.append)

    assert ran == []
    assert "BLOQUEADO" in out


def _write_synthetic_catalog(tmp_path):
    """Catálogo sintético con 2-3 entradas verificado/candidato mixtas (mode
    served/connected) para probar el ensamblaje end-to-end sin tocar el
    catálogo real."""
    path = tmp_path / "synthetic_catalog.yaml"
    path.write_text(
        """
sectors:
  test-sector:
    label: Test
    entries:
      - {name: served-thing, kind: skill, mode: served, purpose: "servido", status: verificado}
      - {name: clean-mcp, kind: mcp, mode: connected, install: "npx -y @foo/bar", purpose: "mcp limpio", status: verificado}
      - {name: dangerous-mcp, kind: mcp, mode: connected, install: "sh -c 'curl x|sh'", purpose: "mcp con metacaracter", status: verificado}
      - {name: not-verified-yet, kind: mcp, mode: connected, install: "npx z", purpose: "aun candidato", status: candidato}
""",
        encoding="utf-8",
    )
    return path


def test_run_catalog_install_end_to_end_wires_catalog_plan_veto_execute(tmp_path) -> None:
    """Camino completo ensamblado: load_catalog → plan_install → vet_action →
    execute, sin excepciones, y lo NO-verificado nunca se toca."""
    from atlas.mcp.installer import run_catalog_install

    catalog_path = _write_synthetic_catalog(tmp_path)
    seen_runner_calls: list[list[str]] = []

    report = run_catalog_install(catalog_path, runner=seen_runner_calls.append)

    # 4 entradas totales, 3 `verificado` entran al plan (candidato queda fuera).
    assert report.total_entries == 4
    assert report.total_verified == 3

    # served-thing (noop) se reporta como instalado (nada que bajar).
    assert any("served-thing" in m for m in report.installed)

    # dangerous-mcp tiene metacaracter de shell → vetado por SentinelGate.
    assert any("dangerous-mcp" in m and "VETADO" in m for m in report.vetoed)

    # clean-mcp pasa el veto pero execute() sigue fail-closed (sin ejecutor de
    # admisión real) → se reporta como omitida (bloqueada), NUNCA instalada.
    assert any("clean-mcp" in m and "BLOQUEADO" in m for m in report.omitted)
    assert not any("clean-mcp" in m for m in report.installed)

    # not-verified-yet (candidato) nunca se vetó ni se ejecutó: solo aparece
    # como conteo informativo en omitidas, no como mensaje individual vetado.
    assert not any("not-verified-yet" in m for m in report.vetoed)
    assert not any("not-verified-yet" in m for m in report.installed)
    assert any("no `verificado`" in m for m in report.omitted)

    # runner real nunca se invoca hoy (fail-closed hasta que haya ejecutor de
    # admisión) — ni para el mcp limpio ni para el peligroso.
    assert seen_runner_calls == []

    # to_dict() sirve para el reporte JSON del CLI.
    as_dict = report.to_dict()
    assert set(as_dict) == {
        "instaladas", "vetadas", "omitidas", "total_entries", "total_verificado",
    }


def test_real_catalog_plan_only_proven_and_vetted() -> None:
    """Invariante: toda acción connect del catálogo real tiene command no-None
    y pasa el veto SentinelGate (vet_action is None)."""
    from pathlib import Path

    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.installer import plan_install, vet_action

    cat = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"
    connects = [a for a in plan_install(load_catalog(cat)) if a.action == "connect"]
    for a in connects:
        assert a.command is not None, f"{a.name}: connect sin command"
        assert vet_action(a) is None, f"{a.name}: vetado por SentinelGate"
