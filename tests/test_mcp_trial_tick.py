"""maintenance_mcp_trial_tick — Pieza 2 cableada al ciclo real (2026-07-23).

Auditoría 2026-07-23: TrialGate/SpawnTrial existían completos y testeados
pero CERO callers de producción -- 777 entradas de catálogo, 0
`probado-en-jaula` para siempre. Este test fija el contrato de producción del
tick que cierra ese círculo, con contenido de skill resoluble localmente
(determinista, sin depender de bwrap/red real).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_MCP_TRIAL", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _write_classified_catalog(repo_root: Path, entries: list[dict]) -> Path:
    design_dir = repo_root / "docs" / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    path = design_dir / "mcp_catalog_classified.yaml"
    doc = {
        "_generated": {"by": "test", "at": "2026-07-23T00:00:00Z"},
        "sectors": {
            "ia-agentes": {"label": "IA y agentes", "entries": entries},
        },
    }
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_disabled_without_env_flag(orch: Orchestrator) -> None:
    assert orch.maintenance_mcp_trial_tick() == {"status": "disabled"}


def test_nested_run_guard_beats_enable_flag(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_TRIAL", "1")
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    assert orch.maintenance_mcp_trial_tick() == {"status": "nested_run_guard"}


def test_no_catalog_file_is_honest_not_silent(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_TRIAL", "1")
    assert orch.maintenance_mcp_trial_tick() == {"status": "no_catalog"}


def test_no_candidates_reports_honestly(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setenv("ATLAS_MCP_TRIAL", "1")
    repo_root = Path(os.environ["ATLAS_CORE_ROOT"])
    _write_classified_catalog(repo_root, [])
    assert orch.maintenance_mcp_trial_tick() == {"status": "no_candidates"}


def test_static_skill_candidate_with_clean_content_gets_promoted(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caso end-to-end real: una skill candidata con contenido local
    resoluble y limpio pasa el escaneo estático y se promueve de verdad,
    persistido en el YAML clasificado -- sin mockear TrialGate."""
    import os

    monkeypatch.setenv("ATLAS_MCP_TRIAL", "1")
    repo_root = Path(os.environ["ATLAS_CORE_ROOT"])

    skills_dir = repo_root / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "my-clean-skill.md").write_text(
        "# My Clean Skill\n\nUna skill benigna de ejemplo, sin nada peligroso.\n",
        encoding="utf-8",
    )

    classified_path = _write_classified_catalog(
        repo_root,
        [
            {
                "name": "my-clean-skill",
                "kind": "skill",
                "purpose": "skill de prueba",
                "status": "candidato",
                "tags": ["test"],
            }
        ],
    )

    result = orch.maintenance_mcp_trial_tick()
    assert result["status"] == "ran"
    assert result["trialed"] == 1
    assert result["promoted"] == 1
    assert result["results"][0]["passed"] is True

    reloaded = yaml.safe_load(classified_path.read_text(encoding="utf-8"))
    entry = reloaded["sectors"]["ia-agentes"]["entries"][0]
    assert entry["status"] == "probado-en-jaula"


def test_batch_size_caps_how_many_are_trialed_per_tick(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un catálogo con más candidatos que el tope por tick no los prueba
    todos de golpe -- acota el gasto/riesgo por ciclo."""
    import os

    from atlas.core.orchestrator_parts import maintenance_facade

    monkeypatch.setenv("ATLAS_MCP_TRIAL", "1")
    repo_root = Path(os.environ["ATLAS_CORE_ROOT"])

    many_entries = [
        {
            "name": f"candidate-{i}",
            "kind": "skill",
            "purpose": "sin contenido local",
            "status": "candidato",
            "tags": ["test"],
        }
        for i in range(maintenance_facade._MCP_TRIAL_BATCH_SIZE + 3)
    ]
    _write_classified_catalog(repo_root, many_entries)

    result = orch.maintenance_mcp_trial_tick()
    assert result["trialed"] == maintenance_facade._MCP_TRIAL_BATCH_SIZE
