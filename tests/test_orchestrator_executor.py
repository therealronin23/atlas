"""
Test de integracion: el cableo D3.4 expone executor + capability_issuer en
Orchestrator y todo encaja end-to-end con el workspace real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.security.capabilities import (
    CapabilityDenied,
    ReadCapability,
    WriteCapability,
)


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    return Orchestrator(workspace=tmp_path / "atlas")


class TestOrchestratorExposesCapabilities:

    def test_executor_and_issuer_accessible(self, orch: Orchestrator) -> None:
        assert orch.executor is not None
        assert orch.capability_issuer is not None
        # Mismo issuer expuesto y referenciado por el executor
        assert orch.executor.issuer is orch.capability_issuer

    def test_issuer_uses_orchestrator_permission_profile(
        self, orch: Orchestrator, tmp_path: Path
    ) -> None:
        # Workspace de Orchestrator: tmp_path/atlas
        target = tmp_path / "atlas" / "tmp" / "scratch.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        cap = orch.capability_issuer.issue_write(target)
        assert isinstance(cap, WriteCapability)
        assert cap.path == target.resolve()

    def test_blocked_path_via_orchestrator_rejected(self, orch: Orchestrator) -> None:
        with pytest.raises(CapabilityDenied):
            orch.capability_issuer.issue_read("/etc/passwd")


class TestEndToEndIOViaOrchestrator:

    def test_write_then_read_roundtrip(self, orch: Orchestrator, tmp_path: Path) -> None:
        target = tmp_path / "atlas" / "tmp" / "round.bin"
        target.parent.mkdir(parents=True, exist_ok=True)

        write_cap = orch.capability_issuer.issue_write(target)
        n = orch.executor.execute_write(write_cap, b"atlas vivo")
        assert n == 10

        read_cap = orch.capability_issuer.issue_read(target)
        data = orch.executor.execute_read(read_cap)
        assert data == b"atlas vivo"

    def test_actions_logged_to_orchestrator_merkle(
        self, orch: Orchestrator, tmp_path: Path
    ) -> None:
        target = tmp_path / "atlas" / "tmp" / "logged.bin"
        target.parent.mkdir(parents=True, exist_ok=True)

        write_cap = orch.capability_issuer.issue_write(target)
        orch.executor.execute_write(write_cap, b"x")

        # La cadena merkle del Orchestrator debe seguir valida tras el log
        ok, _ = orch._merkle.verify_chain()
        assert ok

        # Y el ultimo log debe ser de file.write con AGENT del executor
        recent = orch._merkle.tail(5)
        write_actions = [r for r in recent if r.action == "file.write"]
        assert len(write_actions) >= 1
        assert write_actions[-1].agent == "atlas.executor"


class TestHandleIntentRoutesThroughExecutor:
    """FU-1 — git.* y fs.list_dir van por AtlasExecutor + capability tokens."""

    def test_git_status_logs_exec_command_via_executor(
        self, orch: Orchestrator
    ) -> None:
        orch.handle_intent("git status")
        recent = orch._merkle.tail(10)
        # AtlasExecutor.execute_exec deja un log "exec.command" con agent atlas.executor
        exec_logs = [r for r in recent if r.action == "exec.command"]
        assert len(exec_logs) >= 1, "git status debe pasar por execute_exec"
        assert exec_logs[-1].agent == "atlas.executor"
        # El payload incluye el comando ejecutado
        assert exec_logs[-1].payload.get("command") == "git"

    def test_git_status_result_has_normalized_shape(
        self, orch: Orchestrator
    ) -> None:
        t = orch.handle_intent("git status")
        # _run_via_executor normaliza a {stdout, stderr, returncode, duration_ms}
        # (returncode puede ser non-zero si tmp/ no es un repo git, no importa)
        assert t.result is not None
        assert "returncode" in t.result or "error" in t.result

    def test_fs_list_dir_logs_to_merkle_with_executor_agent(
        self, orch: Orchestrator
    ) -> None:
        orch.handle_intent("lista los archivos del workspace")
        recent = orch._merkle.tail(10)
        list_logs = [r for r in recent if r.action == "fs.list_dir"]
        assert len(list_logs) >= 1
        assert list_logs[-1].agent == "atlas.executor"
