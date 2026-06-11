"""ADR-040 × ADR-025 — `advance_cold_update`: ColdUpdate gobernado por el seam.

Cierra el lazo de los proposers (deps/codegen): TODOS los generadores pasan por
el decisor intercambiable, no solo la adopción MCP. Reglas que estos tests fijan:

- **HumanDecider (default) = paridad:** la propuesta queda `validated` esperando
  el CLI; nada se aplica.
- **AutonomousDecider aplica lo de bajo riesgo anclado** y registra undo real
  (`COLD_PATCH` → `rollback_applied`); `revert(action_hash)` lo deshace.
- **risk=high → sensitivity=high → Deny** (regla constitucional #4): el codegen
  nunca se auto-aplica.
- **Mutación no anclada → Deny + reject.**
- **CERO pytest/mypy reales:** `ValidationRunner` mockeado; ningún subproceso de
  validación real (el patch sí se aplica con git/patch sobre un mini-proyecto
  desechable en tmp_path).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest

from atlas.core.decider import AutonomousDecider
from atlas.core.orchestrator import Orchestrator
from atlas.core.validation_runner import ValidationReport

_OK_REPORT = ValidationReport(
    passed=True,
    pytest_exit=0,
    mypy_exit=0,
    pytest_summary="ok",
    mypy_summary="ok",
)


@pytest.fixture
def mini_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # El hook pre-commit exporta GIT_INDEX_FILE/GIT_DIR; los subprocesos git
    # del test (init/worktree sobre el mini-repo) los heredarían y operarían
    # contra el repo padre. Se limpian para aislar.
    import os

    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)

    root = tmp_path / "project"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "src" / "atlas" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text('[project]\nname="x"\n')
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )
    return root


@pytest.fixture
def orch(
    tmp_path: Path, mini_project: Path, monkeypatch: pytest.MonkeyPatch
) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(mini_project))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


def _bump_patch(tmp_path: Path) -> Path:
    # Bump de la dependencia "uvicorn" en docs (prefijo permitido, contenido simple)
    patch = tmp_path / "bump.patch"
    patch.write_text(
        "--- /dev/null\n+++ b/docs/uvicorn_bump.txt\n@@ -0,0 +1 @@\n+uvicorn 0.30.1\n",
        encoding="utf-8",
    )
    return patch


def _propose(orch: Orchestrator, tmp_path: Path, *, risk: str = "low"):
    return orch.cold_update().propose(
        "bump dependencia uvicorn 0.30.0 → 0.30.1",
        _bump_patch(tmp_path),
        origin="self_audit",
        risk=risk,
        evidence={"dependency": "uvicorn", "from": "0.30.0", "to": "0.30.1"},
    )


def _advance(orch: Orchestrator, proposal_id: str) -> str:
    with mock_patch("atlas.core.cold_update_manager.ValidationRunner") as vr:
        vr.return_value.run.return_value = _OK_REPORT
        return orch.advance_cold_update(proposal_id)


class TestHumanParity:
    def test_human_decider_leaves_validated(self, orch: Orchestrator, tmp_path: Path) -> None:
        p = _propose(orch, tmp_path)
        status = _advance(orch, p.id)
        assert "requiere aprobación humana" in status
        assert orch.cold_update().get(p.id).status == "validated"
        # Nada aplicado en el root
        assert not (Path(orch.cold_update()._root) / "docs" / "uvicorn_bump.txt").exists()

    def test_missing_proposal(self, orch: Orchestrator) -> None:
        assert orch.advance_cold_update("nope").startswith("error:")


class TestAutonomousFlow:
    def test_low_risk_anchored_applies_with_undo(
        self, orch: Orchestrator, tmp_path: Path
    ) -> None:
        orch.set_decider(AutonomousDecider())
        p = _propose(orch, tmp_path, risk="low")
        status = _advance(orch, p.id)
        assert status == f"applied: {p.id}"
        assert orch.cold_update().get(p.id).status == "applied"
        applied_file = Path(orch.cold_update()._root) / "docs" / "uvicorn_bump.txt"
        assert applied_file.exists()

        # El undo quedó atado al action_hash y revert lo deshace
        recs = [r.to_dict() for r in orch._merkle.tail(20)]
        hashes = [
            r["payload"].get("action_hash")
            for r in recs
            if r["action"] == "decider.verdict"
            and r["payload"].get("action_kind") == "cold_update_apply"
        ]
        assert hashes and hashes[-1]
        assert orch.revert(hashes[-1]) is True
        assert orch.cold_update().get(p.id).status == "rolled_back"
        assert not applied_file.exists()

    def test_high_risk_denied_and_rejected(
        self, orch: Orchestrator, tmp_path: Path
    ) -> None:
        orch.set_decider(AutonomousDecider())
        p = _propose(orch, tmp_path, risk="high")
        status = _advance(orch, p.id)
        assert status.startswith("denegado:")
        assert orch.cold_update().get(p.id).status == "rejected"

    def test_unanchored_mutation_denied(
        self, orch: Orchestrator, tmp_path: Path
    ) -> None:
        orch.set_decider(AutonomousDecider())
        # Evidencia (descriptor) sin intersección léxica con el intent → Deny
        p = orch.cold_update().propose(
            "bump dependencia uvicorn 0.30.0 → 0.30.1",
            _bump_patch(tmp_path),
            origin="self_audit",
            risk="low",
            evidence={"x": "zzzqqq wwwfff"},
        )
        status = _advance(orch, p.id)
        assert status.startswith("denegado:")
        assert orch.cold_update().get(p.id).status == "rejected"

    def test_failed_validation_stops(self, orch: Orchestrator, tmp_path: Path) -> None:
        orch.set_decider(AutonomousDecider())
        p = _propose(orch, tmp_path)
        bad = ValidationReport(
            passed=False, pytest_exit=1, mypy_exit=0,
            pytest_summary="1 failed", mypy_summary="ok",
        )
        with mock_patch("atlas.core.cold_update_manager.ValidationRunner") as vr:
            vr.return_value.run.return_value = bad
            status = orch.advance_cold_update(p.id)
        assert status.startswith("validation_failed")
        assert orch.cold_update().get(p.id).status == "failed"
