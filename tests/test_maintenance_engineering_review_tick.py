"""Tests de `maintenance_engineering_review_tick` (ADC-WO-108, 2026-07-30).

`src/atlas/engineering/` tenía 2209 líneas de producción y 1868 de tests, y
CERO callers fuera del propio paquete (verificado por grep en `src/` y
`scripts/`): un plano de coordinación de hallazgos de ingeniería construido,
testeado y nunca cableado. Es el único work order `READY` del canon vivo
(`docs/canon/implementation_registry.yaml`), con la autorización de ejecución
del operador ya registrada.

Este tick es la pieza "Orchestrator integration" del WO. Espejo exacto de
`maintenance_workbench_compliance_review_tick`: opt-in por env
(`ATLAS_ENGINEERING_REVIEW=1`), guardia anti-recursión, cadencia 24h, Merkle.
Compone las piezas que YA existen (baselines + preparer + coordinator +
store); no crea otro verificador -- ese es el riesgo que el propio WO nombra.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    # Segundo commit: sin delta no hay nada que revisar, y el caso realista
    # (repo con historia) es el que interesa medir.
    (root / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "delta")
    return root


@pytest.fixture
def orch(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(repo))
    monkeypatch.delenv("ATLAS_ENGINEERING_REVIEW", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


class TestEngineeringReviewTickDisabledAndGuard:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_engineering_review_tick() == {"status": "disabled"}

    def test_nested_run_guard_beats_enabled_env(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        monkeypatch.setenv("ATLAS_ENGINEERING_REVIEW", "1")
        assert orch.maintenance_engineering_review_tick() == {"status": "nested_run_guard"}


class TestEngineeringReviewTickFirstRun:
    def test_first_run_reviews_head_and_writes_state(
        self, orch: Orchestrator, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_ENGINEERING_REVIEW", "1")

        result = orch.maintenance_engineering_review_tick()

        assert result["status"] == "ran"
        assert result["reviewed"] is True
        assert result["candidate_revision"], "el tick debe registrar qué revisión revisó"

        state_path = repo / "workspace" / "self_build" / "engineering_review_state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["last_run_date"] == datetime.now(timezone.utc).date().isoformat()

    def test_findings_journal_is_created_under_workspace(
        self, orch: Orchestrator, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El plano deja de estar dormido: su journal pasa a existir de verdad."""
        monkeypatch.setenv("ATLAS_ENGINEERING_REVIEW", "1")

        orch.maintenance_engineering_review_tick()

        journal = repo / "workspace" / "engineering" / "findings.jsonl"
        assert journal.parent.is_dir(), "el tick debe materializar el directorio del journal"


class TestEngineeringReviewTickCadence:
    def test_second_call_same_day_is_a_noop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_ENGINEERING_REVIEW", "1")

        first = orch.maintenance_engineering_review_tick()
        second = orch.maintenance_engineering_review_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}


class TestEngineeringReviewTickMerkle:
    def test_merkle_action_logged_with_summary(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_ENGINEERING_REVIEW", "1")

        orch.maintenance_engineering_review_tick()

        records = [
            r for r in orch._merkle.read_all()
            if r.action == "self_maintenance.engineering_review_tick"
        ]
        assert len(records) == 1
        record = records[0]
        assert record.result == "ran"
        assert record.payload["reviewed"] is True
        assert record.payload["candidate_revision"]
