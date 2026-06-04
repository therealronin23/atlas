"""ADR-039 slice 4 — Scheduler cron del front-half.

El ``MaintenanceScheduler`` dispara una pasada descubrir→analizar→notificar y
**nunca aplica**. Reglas que estos tests fijan:

- **CERO red/LLM real:** ``discover`` y ``analyze`` son callables falsos.
- **Solo notifica lo corroborado:** ``analyze`` devuelve ``None`` para lo no
  corroborado (fail-closed del Analyst); esas entradas no llegan a ``notify``.
- **No notifica si no hay propuestas:** sin propuestas, ``notify`` no se llama.
- **Nunca aplica:** la única salida es la lista de propuestas + notificación; no
  hay ningún camino a adopción/ejecución desde el scheduler.
- **Auditoría:** cada tick deja un registro con ``applied=False``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.self_maintenance import (
    PROVENANCE_AUTHORITATIVE,
    MaintenanceScheduler,
    McpCandidate,
    McpProposal,
    Source,
)
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _candidate(name: str, version: str = "1.0.0") -> McpCandidate:
    return McpCandidate(
        name=name,
        version=version,
        cmd=["npx", "-y", name],
        declared_tools=[],
        sources=[Source(PROVENANCE_AUTHORITATIVE, "https://reg/x", "desc")],
    )


def _proposal(cap: str, version: str = "1.0.0") -> McpProposal:
    return McpProposal(
        id=f"mcpprop-{cap}",
        capability=cap,
        version=version,
        cmd=["npx", "-y", cap],
        purpose="x",
        risks=[],
        evidence=[],
    )


class TestTick:
    def test_corroborated_candidates_notified(self, merkle) -> None:
        notified: list[list[McpProposal]] = []
        # analyze corrobora "good", descarta "bad" (None = no corroborado).
        analyze = lambda c: _proposal(c.name) if c.name == "good" else None

        sched = MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: [_candidate("good"), _candidate("bad")],
            analyze=analyze,
            notify=notified.append,
        )
        proposals = sched.tick()

        assert [p.capability for p in proposals] == ["good"]
        assert len(notified) == 1 and [p.capability for p in notified[0]] == ["good"]

    def test_no_proposals_no_notify(self, merkle) -> None:
        called: list[Any] = []
        sched = MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: [_candidate("x"), _candidate("y")],
            analyze=lambda c: None,  # nada corrobora
            notify=called.append,
        )
        assert sched.tick() == []
        assert called == []

    def test_empty_discovery_is_safe(self, merkle) -> None:
        sched = MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: [],
            analyze=lambda c: _proposal(c.name),
            notify=lambda p: None,
        )
        assert sched.tick() == []

    def test_notify_failure_does_not_break_tick(self, merkle) -> None:
        def _boom(proposals):
            raise RuntimeError("telegram caído")

        sched = MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: [_candidate("good")],
            analyze=lambda c: _proposal(c.name),
            notify=_boom,
        )
        # La pasada devuelve las propuestas aunque la notificación falle.
        assert [p.capability for p in sched.tick()] == ["good"]


class TestNeverApplies:
    def test_tick_only_discovers_analyzes_notifies(self, merkle) -> None:
        # Los únicos colaboradores que el scheduler puede tocar son los tres
        # inyectados. No hay seam de adopción/ejecución: si lo hubiera, este test
        # rompería al no encontrar el callable.
        calls: list[str] = []
        MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: calls.append("discover") or [_candidate("good")],
            analyze=lambda c: calls.append("analyze") or _proposal(c.name),
            notify=lambda p: calls.append("notify"),
        ).tick()
        assert calls == ["discover", "analyze", "notify"]


class TestAudit:
    def test_tick_audited_applied_false(self, merkle) -> None:
        MaintenanceScheduler(
            merkle=merkle,
            discover=lambda: [_candidate("good"), _candidate("bad")],
            analyze=lambda c: _proposal(c.name) if c.name == "good" else None,
            notify=lambda p: None,
        ).tick()
        rec = next(
            r.to_dict() for r in merkle.tail(10)
            if r.to_dict()["action"] == "self_maintenance.scheduler_tick"
        )
        assert rec["payload"]["applied"] is False
        assert rec["payload"]["candidate_count"] == 2
        assert rec["payload"]["proposal_count"] == 1
        assert rec["payload"]["proposal_ids"] == ["mcpprop-good"]
