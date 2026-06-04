"""ADR-040 slice 6 — cierre del cabo de captura reversible.

Hilo completo: una mutación reversible pasa por el seam, se ejecuta, deja su
handle de undo real atado al ``action_hash`` que el decisor autorizó, y
``revert(action_hash)`` la deshace. Cubre los DOS productores forward:

  * ``adopt_mcp_server`` → undo ``MCP_SERVER`` (``remove_server``).
  * ``execute_reversible_code`` → undo ``SNAPSHOT`` (``restore_snapshot``).

Antes de este slice ``register_undo`` no tenía ningún llamante en producción y
el ``AutonomousDecider`` denegaba toda mutación (invariante 4, sin undo). Estos
son los únicos call-sites que declaran ``reversible=True``.

Regla de tests del proyecto: nunca lanzar proceso real — la ejecución OMEGA se
mockea (``_sandbox.execute``); el snapshot subyacente sí es real (tarfile) para
que ``revert`` lo restaure de verdad.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import OperationalMode, Task, TaskSource
from atlas.core.decider import (
    MCP_SERVER,
    SNAPSHOT,
    Allow,
    AutonomousDecider,
    DecisionAction,
    Deny,
    HumanDecider,
    action_hash,
)
from atlas.mcp import McpServerConfig
from atlas.security.sandbox import SandboxResult


@pytest.fixture
def orch(tmp_path: Path):
    from atlas.core.orchestrator import Orchestrator
    import atlas.governance.governance_l0 as g

    g.GovernanceL0._instance = None
    ws = tmp_path / "atlas"
    ws.mkdir()
    o = Orchestrator(workspace=ws)
    yield o
    g.GovernanceL0._instance = None


def _expected_hash(kind: str, descriptor: str, intent: str) -> str:
    """Recalcula el hash que el orquestador atará al undo (reason se excluye)."""
    return action_hash(
        DecisionAction(
            kind=kind,
            requires_approval=True,
            mutating=True,
            reversible=True,
            sensitivity="low",
            descriptor=descriptor,
        ),
        intent,
    )


class TestAdoptMcpServerReversible:
    def test_autonomous_allows_adopts_and_registers_undo(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        adopted: list[str] = []

        def _add(cfg: McpServerConfig) -> str:
            adopted.append(cfg.name)
            return f"ok: server '{cfg.name}' adoptado"

        monkeypatch.setattr(orch._mcp, "add_server", _add)

        # Intent anclado léxicamente al nombre del server (invariante 3).
        task = Task(intent="adopta el server weather", source=TaskSource.CLI)
        cfg = McpServerConfig(name="weather", cmd=["weather-mcp"])

        status = orch.adopt_mcp_server(cfg, task)

        assert status.startswith("ok:")
        assert adopted == ["weather"]
        h = _expected_hash("mcp_adopt", "weather", task.intent)
        handle = orch._revert_registry.get(h)
        assert handle is not None
        assert handle.kind == MCP_SERVER and handle.ref == "weather"

    def test_full_cycle_revert_removes_server(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        removed: list[str] = []
        monkeypatch.setattr(
            orch._mcp, "add_server", lambda cfg: f"ok: server '{cfg.name}' adoptado"
        )
        monkeypatch.setattr(
            orch._mcp, "remove_server", lambda name: removed.append(name) or True
        )

        task = Task(intent="adopta el server weather", source=TaskSource.CLI)
        cfg = McpServerConfig(name="weather", cmd=["weather-mcp"])
        orch.adopt_mcp_server(cfg, task)

        h = _expected_hash("mcp_adopt", "weather", task.intent)
        assert orch.revert(h) is True
        assert removed == ["weather"]
        # Handle consumido tras el revert.
        assert orch._revert_registry.get(h) is None

    def test_unanchored_descriptor_denied_no_undo(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        called: list[str] = []
        monkeypatch.setattr(
            orch._mcp, "add_server", lambda cfg: called.append(cfg.name) or "ok:"
        )
        # Descriptor no anclado en la intención → invariante 3 → Deny.
        task = Task(intent="haz algo distinto", source=TaskSource.CLI)
        cfg = McpServerConfig(name="weather", cmd=["weather-mcp"])

        status = orch.adopt_mcp_server(cfg, task)

        assert status.startswith("denegado:")
        assert called == []  # no se ejecutó la mutación
        h = _expected_hash("mcp_adopt", "weather", task.intent)
        assert orch._revert_registry.get(h) is None

    def test_human_decider_requires_human_no_execute(self, orch, monkeypatch) -> None:
        orch.set_decider(HumanDecider())
        called: list[str] = []
        monkeypatch.setattr(
            orch._mcp, "add_server", lambda cfg: called.append(cfg.name) or "ok:"
        )
        task = Task(intent="adopta el server weather", source=TaskSource.CLI)
        cfg = McpServerConfig(name="weather", cmd=["weather-mcp"])

        status = orch.adopt_mcp_server(cfg, task)

        assert "humana" in status
        assert called == []

    def test_failed_add_does_not_register_undo(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        monkeypatch.setattr(
            orch._mcp, "add_server", lambda cfg: "error: no arrancó"
        )
        task = Task(intent="adopta el server weather", source=TaskSource.CLI)
        cfg = McpServerConfig(name="weather", cmd=["weather-mcp"])

        status = orch.adopt_mcp_server(cfg, task)

        assert status.startswith("error:")
        h = _expected_hash("mcp_adopt", "weather", task.intent)
        assert orch._revert_registry.get(h) is None


class TestExecuteReversibleCodeSnapshot:
    def test_autonomous_executes_and_registers_snapshot(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        # Snapshot real del workspace; la ejecución (subprocess) se mockea.
        snap_id = orch._sandbox._take_snapshot(orch._workspace)

        def _fake_execute(**kwargs):
            assert kwargs["take_snapshot"] is True
            assert kwargs["operational_mode"] == OperationalMode.OMEGA
            return SandboxResult(
                success=True, stdout="", stderr="", exit_code=0,
                duration_ms=1, operational_mode=OperationalMode.OMEGA,
                snapshot_id=snap_id,
            )

        monkeypatch.setattr(orch._sandbox, "execute", _fake_execute)

        task = Task(intent="escribe un archivo nuevo", source=TaskSource.CLI)
        result = orch.execute_reversible_code(
            "open('x','w').write('1')", task, descriptor="escribe archivo"
        )

        assert result is not None and result.snapshot_id == snap_id
        h = _expected_hash("omega_exec", "escribe archivo", task.intent)
        handle = orch._revert_registry.get(h)
        assert handle is not None and handle.kind == SNAPSHOT and handle.ref == snap_id

        # Ciclo completo: revert restaura el snapshot real y olvida el handle.
        assert orch.revert(h) is True
        assert orch._revert_registry.get(h) is None

    def test_denied_does_not_execute(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        ran: list[bool] = []
        monkeypatch.setattr(
            orch._sandbox, "execute", lambda **k: ran.append(True)
        )
        # Descriptor no anclado → Deny → None, sin ejecución.
        task = Task(intent="objetivo totalmente distinto", source=TaskSource.CLI)
        result = orch.execute_reversible_code(
            "x=1", task, descriptor="formatea disco"
        )
        assert result is None
        assert ran == []


class TestActionHashThreadsToExecution:
    def test_consult_decider_returns_hash(self, orch) -> None:
        task = Task(intent="x", source=TaskSource.CLI)
        verdict, h = orch._consult_decider(DecisionAction(kind="route"), task)
        assert isinstance(verdict, (Allow, Deny)) or h
        assert len(h) == 64
