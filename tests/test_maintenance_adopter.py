"""ADR-039 slice 3 — wire propuesta → adopción.

Dos niveles:

- **Unit** (``TestAdopterWiring``): el adopter traduce ``McpProposal`` →
  ``McpServerConfig`` + ``Task`` y delega en el callable ``adopt`` inyectado.
  Verifica cfg/task/intent-anclada/auditoría sin orquestador real.
- **E2E** (``TestAdopterEndToEnd``): orquestador real. Con ``AutonomousDecider``
  e intención anclada el server se adopta de verdad (``add_server`` mockeado) y
  queda el undo reversible. Con el ``HumanDecider`` por defecto el seam exige
  aprobación y nada se adopta.

Regla del proyecto: nunca se lanza un proceso real — ``add_server`` se mockea.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import Task, TaskSource
from atlas.core.decider import AutonomousDecider, action_hash
from atlas.core.decider import DecisionAction, MCP_SERVER
from atlas.core.self_maintenance import MaintenanceAdopter, McpProposal
from atlas.mcp import McpServerConfig
from atlas.logging.merkle_logger import MerkleLogger


def _proposal(*, capability="fs-mcp", version="1.2.0") -> McpProposal:
    return McpProposal(
        id="mcpprop-deadbeef0001",
        capability=capability,
        version=version,
        cmd=["npx", "-y", "@modelcontextprotocol/server-filesystem"],
        purpose="acceso FS",
        risks=["acceso a disco"],
        evidence=[],
    )


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


class TestAdopterWiring:
    def test_translates_proposal_to_cfg_and_task(self, merkle) -> None:
        seen: dict = {}

        def _adopt(cfg: McpServerConfig, task: Task) -> str:
            seen["cfg"] = cfg
            seen["task"] = task
            return f"ok: server '{cfg.name}' adoptado"

        status = MaintenanceAdopter(adopt=_adopt, merkle=merkle).adopt(_proposal())

        assert status.startswith("ok:")
        cfg, task = seen["cfg"], seen["task"]
        assert cfg.name == "fs-mcp"
        assert cfg.cmd == ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
        assert task.source == TaskSource.INTERNAL
        # Intención anclada léxicamente al nombre del server (invariante 3).
        assert "fs-mcp" in task.intent and "1.2.0" in task.intent

    def test_pending_status_passthrough(self, merkle) -> None:
        status = MaintenanceAdopter(
            adopt=lambda cfg, task: "requiere aprobación humana para adoptar el server",
            merkle=merkle,
        ).adopt(_proposal())
        assert "aprobación humana" in status

    def test_denied_status_passthrough(self, merkle) -> None:
        status = MaintenanceAdopter(
            adopt=lambda cfg, task: "denegado: mutación no anclada",
            merkle=merkle,
        ).adopt(_proposal())
        assert status.startswith("denegado:")


class TestAdopterAudit:
    def test_adopted_audited(self, merkle) -> None:
        MaintenanceAdopter(
            adopt=lambda cfg, task: "ok: adoptado", merkle=merkle
        ).adopt(_proposal())
        rec = next(
            r.to_dict() for r in merkle.tail(10)
            if r.to_dict()["action"] == "self_maintenance.adopter_adopt"
        )
        assert rec["result"] == "adopted"
        assert rec["payload"]["adopted"] is True
        assert rec["payload"]["proposal_id"] == "mcpprop-deadbeef0001"

    def test_not_adopted_audited(self, merkle) -> None:
        MaintenanceAdopter(
            adopt=lambda cfg, task: "requiere aprobación humana", merkle=merkle
        ).adopt(_proposal())
        rec = next(
            r.to_dict() for r in merkle.tail(10)
            if r.to_dict()["action"] == "self_maintenance.adopter_adopt"
        )
        assert rec["result"] == "not_adopted"
        assert rec["payload"]["adopted"] is False

    def test_audit_failure_does_not_break(self, merkle, monkeypatch) -> None:
        def _boom(*a, **k):
            raise RuntimeError("merkle caído")

        monkeypatch.setattr(merkle, "log", _boom)
        status = MaintenanceAdopter(
            adopt=lambda cfg, task: "ok: adoptado", merkle=merkle
        ).adopt(_proposal())
        assert status.startswith("ok:")


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


class TestAdopterEndToEnd:
    def test_autonomous_adopts_and_registers_undo(self, orch, monkeypatch) -> None:
        orch.set_decider(AutonomousDecider())
        adopted: list[str] = []
        monkeypatch.setattr(
            orch._mcp, "add_server",
            lambda cfg: adopted.append(cfg.name) or f"ok: server '{cfg.name}' adoptado",
        )

        status = orch.maintenance_adopter().adopt(_proposal(capability="weather"))

        assert status.startswith("ok:")
        assert adopted == ["weather"]
        # El undo reversible quedó atado al action_hash que el decisor autorizó.
        h = action_hash(
            DecisionAction(
                kind="mcp_adopt",
                requires_approval=True,
                mutating=True,
                reversible=True,
                sensitivity="low",
                descriptor="weather",
            ),
            "adopta el server MCP weather v1.2.0",
        )
        handle = orch._revert_registry.get(h)
        assert handle is not None and handle.kind == MCP_SERVER and handle.ref == "weather"

    def test_human_decider_requires_approval_no_adopt(self, orch, monkeypatch) -> None:
        # Default = HumanDecider: el seam exige aprobación, nada se adopta.
        called: list[str] = []
        monkeypatch.setattr(
            orch._mcp, "add_server", lambda cfg: called.append(cfg.name) or "ok:"
        )

        status = orch.maintenance_adopter().adopt(_proposal(capability="weather"))

        assert "aprobación humana" in status
        assert called == []
