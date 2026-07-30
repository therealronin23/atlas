"""Tests de `maintenance_provider_status_tick` (2026-07-30, pedido directo del
operador: sincronizarse con la página de estado pública de cada proveedor).

Espejo exacto de `maintenance_provider_discovery_tick`: opt-in por env
(`ATLAS_PROVIDER_STATUS=1`), guardia anti-recursión
(`ATLAS_NESTED_TEST_RUN=1`), cadencia 24h vía fichero de estado
(`workspace/self_build/provider_status_state.json`), acción Merkle
`self_maintenance.provider_status_tick`. Corre `check_provider_status`
(`provider_status.py`) -- cero llamadas de inferencia, cero red real en los
tests (`check_provider_status` se monkeypatchea siempre).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.provider_status import StatusResult


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_PROVIDER_STATUS", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _fake_check_all_operational(providers: object, **_: object) -> list[StatusResult]:
    return [
        StatusResult(vendor="groq", outcome="ok", state="operational", reason="sin incidentes"),
        StatusResult(vendor="together", outcome="ok", state="operational", reason="sin incidentes"),
        StatusResult(vendor="google", outcome="ok", state="operational", reason="sin incidentes"),
        StatusResult(vendor="openrouter", outcome="no_public_status_page", state="unknown", reason="sin endpoint"),
        StatusResult(vendor="nvidia", outcome="no_public_status_page", state="unknown", reason="sin endpoint"),
    ]


def _fake_check_one_degraded(providers: object, **_: object) -> list[StatusResult]:
    return [
        StatusResult(vendor="groq", outcome="ok", state="degraded", reason="incidente en curso"),
        StatusResult(vendor="together", outcome="ok", state="operational", reason="sin incidentes"),
    ]


class TestProviderStatusTickDisabledAndGuard:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_provider_status_tick() == {"status": "disabled"}

    def test_nested_run_guard_beats_missing_env_and_enabled_env(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        assert orch.maintenance_provider_status_tick() == {"status": "nested_run_guard"}

        monkeypatch.setenv("ATLAS_PROVIDER_STATUS", "1")
        assert orch.maintenance_provider_status_tick() == {"status": "nested_run_guard"}


class TestProviderStatusTickFirstRun:
    def test_first_run_writes_state_with_last_run_date_and_results(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_STATUS", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.check_provider_status",
            _fake_check_all_operational,
        )

        result = orch.maintenance_provider_status_tick()

        assert result["status"] == "ran"
        assert result["degraded"] == []
        assert result["unmonitored"]  # openrouter, nvidia

        state_path = (
            Path(str(orch._project_root()))
            / "workspace" / "self_build" / "provider_status_state.json"
        )
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "last_run_date" in state
        assert isinstance(state["last_results"], list)
        first = state["last_results"][0]
        assert {"vendor", "outcome", "state", "reason", "checked_at"} <= first.keys()

    def test_first_run_reports_degraded_vendor(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_STATUS", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.check_provider_status",
            _fake_check_one_degraded,
        )

        result = orch.maintenance_provider_status_tick()

        assert result["status"] == "ran"
        assert result["degraded"] == ["groq"]


class TestProviderStatusTickCadence:
    def test_second_call_same_day_is_a_noop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_STATUS", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.check_provider_status",
            _fake_check_all_operational,
        )

        first = orch.maintenance_provider_status_tick()
        second = orch.maintenance_provider_status_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}


class TestProviderStatusTickMerkle:
    def test_merkle_action_logged_with_summary(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_STATUS", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.check_provider_status",
            _fake_check_one_degraded,
        )

        orch.maintenance_provider_status_tick()

        records = [
            r for r in orch._merkle.read_all()
            if r.action == "self_maintenance.provider_status_tick"
        ]
        assert len(records) == 1
        record = records[0]
        assert record.result == "ran"
        assert "degraded" in record.payload
        assert record.payload["degraded"] == ["groq"]


class TestProviderStatusTickIsolatedCycle:
    def test_registered_alongside_provider_discovery_cycle_in_scheduler(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scheduler = orch.maintenance_scheduler()
        assert len(scheduler._extra_cycles) >= 9
