"""ADR-039 — cierre del lazo autónomo (scheduler → adopter → decisor).

Reglas que estos tests fijan:

- **Notify enruta al adopter:** cuando el scheduler notifica propuestas, la
  clausura del orquestador las pasa al ``MaintenanceAdopter``, que consulta el
  seam del decisor (ADR-040). El scheduler no adopta por sí solo.
- **Decisor gatea apply:** bajo ``HumanDecider`` (default) el seam devuelve
  "requiere aprobación humana" y ``add_server`` no se invoca — paridad con HITL.
- **Arranque gateado por env:** el ``AtlasServiceRunner`` solo arranca el
  scheduler cuando ``ATLAS_MAINTENANCE_SCHEDULER=1``; por defecto no lo hace.
- **Stop limpio:** el runner llama ``stop()`` al scheduler activo.
- **CERO red/LLM real:** todas las dependencias son fakes inyectados.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance import (
    PROVENANCE_AUTHORITATIVE,
    McpCandidate,
    McpProposal,
    Source,
)
from atlas.runtime.service_runner import AtlasServiceRunner


# ---------------------------------------------------------------------------
# Fixtures compartidos
# ---------------------------------------------------------------------------


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


def _candidate(name: str = "mcp-test") -> McpCandidate:
    return McpCandidate(
        name=name,
        version="1.0.0",
        cmd=["npx", "-y", name],
        declared_tools=["read"],
        sources=[Source(PROVENANCE_AUTHORITATIVE, "https://reg/x", "desc")],
    )


def _proposal(cap: str = "mcp-test") -> McpProposal:
    return McpProposal(
        id=f"mcpprop-{cap}",
        capability=cap,
        version="1.0.0",
        cmd=["npx", "-y", cap],
        purpose="test",
        risks=[],
        evidence=[],
    )


# ---------------------------------------------------------------------------
# Tests del cierre de lazo vía el decisor
# ---------------------------------------------------------------------------


class TestNotifyRoutesToAdopter:
    def test_notify_calls_adopter_adopt(self, orch: Orchestrator) -> None:
        """El closure de notify del scheduler pasa cada propuesta al adopter."""
        adopted: list[str] = []

        class _FakeAdopter:
            def adopt(self, proposal: McpProposal) -> str:
                adopted.append(proposal.capability)
                return "requiere aprobación humana"

        # Construir el scheduler (fija la clausura notify)
        scheduler = orch.maintenance_scheduler()
        # Inyectar el adopter falso ANTES de que se ejecute la notify
        orch._maintenance_adopter = _FakeAdopter()  # type: ignore[assignment]

        prop = _proposal("mcp-test")
        # Reemplazar los colaboradores del scheduler para un tick determinista
        scheduler._discover = lambda: [_candidate()]
        scheduler._analyze = lambda c: prop

        scheduler.tick()

        assert adopted == ["mcp-test"]

    def test_notify_still_publishes_event(self, orch: Orchestrator) -> None:
        """La notify publica MAINTENANCE_PROPOSED además de enrutar al adopter."""
        from atlas.core.contracts import EventType

        events: list[str] = []
        orch.bus.subscribe(
            EventType.MAINTENANCE_PROPOSED,
            lambda e: events.append(e.type.value),
        )

        scheduler = orch.maintenance_scheduler()
        orch._maintenance_adopter = type(  # type: ignore[assignment]
            "_NullAdopter", (), {"adopt": lambda self, p: "requiere aprobación humana"}
        )()

        prop = _proposal("mcp-test")
        scheduler._discover = lambda: [_candidate()]
        scheduler._analyze = lambda c: prop
        scheduler.tick()

        assert EventType.MAINTENANCE_PROPOSED.value in events

    def test_human_decider_no_add_server(self, orch: Orchestrator) -> None:
        """Bajo HumanDecider (default) el adopter devuelve 'requiere aprobación humana'
        y add_server no se invoca (paridad con el HITL de hoy)."""
        add_server_calls: list[Any] = []
        original_add_server = orch._mcp.add_server
        orch._mcp.add_server = lambda cfg: add_server_calls.append(cfg) or "skipped"  # type: ignore[method-assign]

        scheduler = orch.maintenance_scheduler()
        prop = _proposal("mcp-test")
        scheduler._discover = lambda: [_candidate()]
        scheduler._analyze = lambda c: prop
        scheduler.tick()

        # add_server nunca se llama bajo HumanDecider
        assert add_server_calls == []
        orch._mcp.add_server = original_add_server  # restaurar

    def test_no_proposals_adopter_not_called(self, orch: Orchestrator) -> None:
        """Sin propuestas corroboradas, el adopter no se invoca."""
        adopted: list[str] = []

        class _FakeAdopter:
            def adopt(self, proposal: McpProposal) -> str:
                adopted.append(proposal.capability)
                return "ok:"

        scheduler = orch.maintenance_scheduler()
        orch._maintenance_adopter = _FakeAdopter()  # type: ignore[assignment]
        scheduler._discover = lambda: [_candidate()]
        scheduler._analyze = lambda c: None  # ninguna corrobora
        scheduler.tick()

        assert adopted == []


class TestDepCycleWiring:
    def test_dep_cycle_chains_scout_proposer_advance(self, orch: Orchestrator) -> None:
        """El extra-cycle de deps encadena discover → propose_bump →
        advance_cold_update por cada candidato."""
        from types import SimpleNamespace

        advanced: list[str] = []

        # Fakes inyectados en los accessors (cero red/git real).
        cand = SimpleNamespace(name="uvicorn")
        orch._maintenance_dep_scout = SimpleNamespace(  # type: ignore[assignment]
            discover=lambda: [cand]
        )
        orch._maintenance_dep_proposer = SimpleNamespace(  # type: ignore[assignment]
            propose_bump=lambda c: SimpleNamespace(id="cu-uvicorn")
        )
        orch.advance_cold_update = lambda pid: advanced.append(pid) or "applied"  # type: ignore[assignment, method-assign]

        # Adopter falso para que la pasada MCP no haga nada real.
        orch._maintenance_adopter = SimpleNamespace(  # type: ignore[assignment]
            adopt=lambda p: "ok:"
        )

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []  # sin candidatos MCP
        scheduler.tick()

        assert advanced == ["cu-uvicorn"]

    def test_dep_cycle_skips_when_no_proposal(self, orch: Orchestrator) -> None:
        from types import SimpleNamespace

        advanced: list[str] = []
        orch._maintenance_dep_scout = SimpleNamespace(  # type: ignore[assignment]
            discover=lambda: [SimpleNamespace(name="x")]
        )
        orch._maintenance_dep_proposer = SimpleNamespace(  # type: ignore[assignment]
            propose_bump=lambda c: None  # no_target / sin bump
        )
        orch.advance_cold_update = lambda pid: advanced.append(pid)  # type: ignore[assignment, method-assign]
        orch._maintenance_adopter = SimpleNamespace(adopt=lambda p: "ok:")  # type: ignore[assignment]

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        scheduler.tick()

        assert advanced == []


# ---------------------------------------------------------------------------
# Tests del arranque del scheduler en el service runner
# ---------------------------------------------------------------------------


class TestBatchCycleWiring:
    """`_batch_cycle` — notificación proactiva de lote de self_audit listo (ver
    ADR de auto-auditoría). Usa un batcher FAKE inyectado, no el real."""

    def test_batch_ready_publishes_event_with_included(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from atlas.core.cold_update_batcher import BatchResult
        from atlas.core.contracts import EventType

        result = BatchResult(
            id="batch-1",
            included=["cu-1", "cu-2"],
            excluded=[{"proposal_id": "cu-3", "reason": "rompe algo"}],
            passed=True,
            pytest_summary="1 passed" * 400,  # más largo que 500 chars
            mypy_summary="",
            worktree_path=None,
        )
        fake_batcher = SimpleNamespace(run_batch=lambda: result)
        orch.maintenance_cold_update_batcher = lambda: fake_batcher  # type: ignore[method-assign]

        intents = {"cu-1": SimpleNamespace(intent="bump uvicorn"),
                   "cu-2": SimpleNamespace(intent="fix lint")}
        orch.cold_update = lambda: SimpleNamespace(get=lambda pid: intents.get(pid))  # type: ignore[method-assign]

        events: list[Any] = []
        orch.bus.subscribe(
            EventType.COLD_UPDATE_BATCH_READY,
            lambda e: events.append(e.payload),
        )

        # No MCP candidates — aislar el _batch_cycle
        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]
        scheduler.tick()

        assert len(events) == 1
        payload = events[0]
        assert payload["batch_id"] == "batch-1"
        assert payload["included"] == ["cu-1", "cu-2"]
        assert payload["included_intents"] == ["bump uvicorn", "fix lint"]
        assert payload["excluded"] == [{"proposal_id": "cu-3", "reason": "rompe algo"}]
        assert payload["tests_passed"] is True
        assert len(payload["pytest_summary"]) <= 500

    def test_batch_empty_included_no_event(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from atlas.core.cold_update_batcher import BatchResult
        from atlas.core.contracts import EventType

        result = BatchResult(
            id="batch-2",
            included=[],
            excluded=[],
            passed=True,
            pytest_summary="",
            mypy_summary="",
            worktree_path=None,
        )
        fake_batcher = SimpleNamespace(run_batch=lambda: result)
        orch.maintenance_cold_update_batcher = lambda: fake_batcher  # type: ignore[method-assign]

        events: list[Any] = []
        orch.bus.subscribe(
            EventType.COLD_UPDATE_BATCH_READY,
            lambda e: events.append(e.payload),
        )

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]
        scheduler.tick()

        assert events == []


class TestSelfBuildCycleWiring:
    """`_self_build_cycle` — autoconstrucción: muele UN item pending del backlog
    por ciclo, opt-in vía ``ATLAS_SELF_BUILD=1``. Un item por tick acota el
    gasto (LLM real); el runner es FAKE inyectado, cero red/LLM real."""

    def _pending_item(self, id_: str = "item-1") -> Any:
        from atlas.core.self_maintenance.backlog import BacklogItem

        return BacklogItem(
            id=id_,
            title=f"title-{id_}",
            why="why",
            targets=(),
            acceptance="acceptance",
            priority=1,
            status="pending",
        )

    def test_without_env_runner_not_called(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin ATLAS_SELF_BUILD en el entorno, el ciclo no toca el runner ni
        el backlog (return temprano, antes de tocar nada)."""
        from types import SimpleNamespace

        monkeypatch.delenv("ATLAS_SELF_BUILD", raising=False)

        calls: list[Any] = []
        fake_runner = SimpleNamespace(run_item=lambda item: calls.append(item))
        orch._maintenance_self_build_runner = fake_runner  # type: ignore[assignment]

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]
        scheduler.tick()

        assert calls == []

    def test_with_env_and_one_pending_item_runs_once(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from atlas.core.self_maintenance import backlog as backlog_mod

        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        item = self._pending_item("item-1")
        monkeypatch.setattr(backlog_mod, "load_backlog", lambda path: [item])

        calls: list[Any] = []
        fake_runner = SimpleNamespace(run_item=lambda item: calls.append(item))
        orch._maintenance_self_build_runner = fake_runner  # type: ignore[assignment]

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]
        scheduler.tick()

        assert calls == [item]

    def test_two_pending_items_only_first_processed(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from atlas.core.self_maintenance import backlog as backlog_mod

        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        item1 = self._pending_item("item-1")
        item2 = self._pending_item("item-2")
        monkeypatch.setattr(backlog_mod, "load_backlog", lambda path: [item1, item2])

        calls: list[Any] = []
        fake_runner = SimpleNamespace(run_item=lambda item: calls.append(item))
        orch._maintenance_self_build_runner = fake_runner  # type: ignore[assignment]

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]
        scheduler.tick()

        assert calls == [item1]

    def test_run_item_exception_does_not_propagate(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from atlas.core.self_maintenance import backlog as backlog_mod

        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        item = self._pending_item("item-1")
        monkeypatch.setattr(backlog_mod, "load_backlog", lambda path: [item])

        def _boom(item: Any) -> None:
            raise RuntimeError("boom")

        fake_runner = SimpleNamespace(run_item=_boom)
        orch._maintenance_self_build_runner = fake_runner  # type: ignore[assignment]

        scheduler = orch.maintenance_scheduler()
        scheduler._discover = lambda: []
        orch._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])  # type: ignore[assignment]

        scheduler.tick()  # no debe propagar la excepción


class TestServiceRunnerSchedulerGate:
    def _base_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Desactiva todos los subsistemas opcionales para aislar el scheduler."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("ATLAS_PROMETHEUS", raising=False)
        monkeypatch.delenv("ATLAS_SERVE_DASHBOARD", raising=False)
        monkeypatch.delenv("ATLAS_THERMAL_MONITOR", raising=False)

    def test_scheduler_not_started_by_default(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._base_env(monkeypatch)
        monkeypatch.delenv("ATLAS_MAINTENANCE_SCHEDULER", raising=False)
        runner = AtlasServiceRunner(orch)
        runner.start()
        # Sin la env, el scheduler ni se construye
        assert orch._maintenance_scheduler is None
        runner.stop()

    def test_scheduler_started_when_env_set(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_MAINTENANCE_SCHEDULER", "1")
        # Cadencia cortísima para que el test no bloquee
        monkeypatch.setenv("ATLAS_MAINTENANCE_POLL_S", "86400")
        runner = AtlasServiceRunner(orch)
        runner.start()
        sched = orch._maintenance_scheduler
        assert sched is not None
        assert sched._running is True
        runner.stop()
        assert sched._running is False

    def test_scheduler_stopped_on_runner_stop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_MAINTENANCE_SCHEDULER", "1")
        monkeypatch.setenv("ATLAS_MAINTENANCE_POLL_S", "86400")
        runner = AtlasServiceRunner(orch)
        runner.start()
        runner.stop()
        assert orch._maintenance_scheduler._running is False
