"""Cierre del gap 'GoldenRoute implementado pero huérfano de wiring' (Cycle 3,
ATLAS PRIME 2026-07-22, ver WORK_LEDGER). GoldenRoute existía con 5 tests E2E
pero CERO callers de producción — nada en CLI/API lo invocaba.

Wiring mínimo: ``Orchestrator.golden_route()`` reusa el MISMO
ColdUpdateManager/MerkleLogger que ``cold_update()`` (no un store aislado vía
``GoldenRoute.for_repo()``, que el propio docstring reserva para tests/fixtures)
— así una propuesta creada por la ruta dorada es indistinguible, para
``atlas update validate/approve/apply``, de una creada a mano. Solo se añade
el paso `request` (texto libre → patch); aprobar/aplicar sigue siendo
exactamente el mismo camino humano que ya existía (norma del spec: la
escritura de misiones sigue siendo CLI humano)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlas.core.orchestrator import Orchestrator
from atlas.interfaces.cli import cli
from atlas.missions.golden_route import GoldenRoute


@pytest.fixture
def mini_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text("primera línea\n")

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


class TestOrchestratorGoldenRoute:
    def test_golden_route_returns_golden_route_instance(self, orch: Orchestrator) -> None:
        assert isinstance(orch.golden_route(), GoldenRoute)

    def test_golden_route_shares_cold_update_manager(self, orch: Orchestrator) -> None:
        """Sin esto, una propuesta creada por la ruta dorada no aparecería en
        `atlas update status` — dos ledgers desconectados, doble estado."""
        gr = orch.golden_route()
        session = gr.request('añade la línea "hola" al final de docs/notes.md')
        assert orch.cold_update().get(session.proposal_id) is not None

    def test_golden_route_is_cached_like_cold_update(self, orch: Orchestrator) -> None:
        assert orch.golden_route() is orch.golden_route()


class TestGoldenRouteCli:
    def test_request_command_creates_proposal_visible_in_update_status(
        self, orch: Orchestrator, mini_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["golden-route", "request", 'añade la línea "hola" al final de docs/notes.md'],
        )
        assert result.exit_code == 0, result.output
        assert "docs/notes.md" in result.output

        status = runner.invoke(cli, ["update", "status"])
        assert status.exit_code == 0, status.output
        # El proposal de la ruta dorada debe listarse igual que uno manual.
        assert "notes.md" in status.output or "hola" in status.output.lower()

    def test_request_command_rejects_unsupported_path(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["golden-route", "request", "refactoriza el orchestrator entero"],
        )
        assert result.exit_code != 0
        assert "v0 solo sabe" in result.output
