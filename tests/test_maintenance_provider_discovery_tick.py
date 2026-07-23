"""Tests de `maintenance_provider_discovery_tick` (T6, plan
2026-07-23-t5-provider-discovery-plan.md).

Espejo exacto de `maintenance_provider_smoke_tick` (T5.1): opt-in por env
(`ATLAS_PROVIDER_DISCOVERY=1`), guardia anti-recursión
(`ATLAS_NESTED_TEST_RUN=1`), cadencia 24h vía fichero de estado
(`workspace/self_build/provider_discovery_state.json`), acción Merkle
`self_maintenance.provider_discovery_tick`. La diferencia con el smoke: en
vez de `ProviderChainSmoke` (que SÍ llama al proveedor), este tick corre
`ModelCatalogDrift` (T4) sobre `discover_available_models` (T3) -- cero
tokens de inferencia, cero red real en los tests (`discover_available_models`
se monkeypatchea siempre).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.provider_discovery import DiscoveryResult


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_PROVIDER_DISCOVERY", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _fake_discover_all_present(provider: object) -> DiscoveryResult:
    """Simula que TODOS los proveedores siguen sirviendo su model_id
    configurado -- outcome='present' para cada uno."""
    from atlas.core.inference_hub import Provider

    assert isinstance(provider, Provider)
    return DiscoveryResult(
        provider_name=provider.name,
        outcome="ok",
        model_ids=[provider.model_id],
        reason="",
    )


def _fake_discover_one_missing(provider: object) -> DiscoveryResult:
    """Simula que el PRIMER provider de DEFAULT_PROVIDERS ya no sirve su
    model_id configurado (catálogo vacío) -- el resto sigue presente."""
    from atlas.core.inference_hub import DEFAULT_PROVIDERS, Provider

    assert isinstance(provider, Provider)
    if provider is DEFAULT_PROVIDERS[0]:
        return DiscoveryResult(
            provider_name=provider.name, outcome="ok", model_ids=[], reason="",
        )
    return DiscoveryResult(
        provider_name=provider.name,
        outcome="ok",
        model_ids=[provider.model_id],
        reason="",
    )


class TestProviderDiscoveryTickDisabledAndGuard:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_provider_discovery_tick() == {"status": "disabled"}

    def test_nested_run_guard_beats_missing_env_and_enabled_env(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        assert orch.maintenance_provider_discovery_tick() == {"status": "nested_run_guard"}

        monkeypatch.setenv("ATLAS_PROVIDER_DISCOVERY", "1")
        assert orch.maintenance_provider_discovery_tick() == {"status": "nested_run_guard"}


class TestProviderDiscoveryTickFirstRun:
    def test_first_run_writes_state_with_last_run_date_and_results(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_DISCOVERY", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.discover_available_models",
            _fake_discover_all_present,
        )

        result = orch.maintenance_provider_discovery_tick()

        assert result["status"] == "ran"
        assert result["present"]  # al menos un provider presente
        assert result["missing"] == []

        state_path = (
            Path(str(orch._project_root()))
            / "workspace" / "self_build" / "provider_discovery_state.json"
        )
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "last_run_date" in state
        assert isinstance(state["last_results"], list)
        assert len(state["last_results"]) > 0
        # cada resultado serializado trae los campos de CatalogDriftResult
        first = state["last_results"][0]
        assert {"provider_name", "configured_model", "present", "outcome", "reason"} <= first.keys()

    def test_first_run_reports_missing_model(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from atlas.core.inference_hub import DEFAULT_PROVIDERS

        monkeypatch.setenv("ATLAS_PROVIDER_DISCOVERY", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.discover_available_models",
            _fake_discover_one_missing,
        )

        result = orch.maintenance_provider_discovery_tick()

        assert result["status"] == "ran"
        assert DEFAULT_PROVIDERS[0].name in result["missing"]
        assert len(result["present"]) == len(DEFAULT_PROVIDERS) - 1


class TestProviderDiscoveryTickCadence:
    def test_second_call_same_day_is_a_noop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_DISCOVERY", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.discover_available_models",
            _fake_discover_all_present,
        )

        first = orch.maintenance_provider_discovery_tick()
        second = orch.maintenance_provider_discovery_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}


class TestProviderDiscoveryTickMerkle:
    def test_merkle_action_logged_with_summary(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_DISCOVERY", "1")
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade.discover_available_models",
            _fake_discover_one_missing,
        )

        orch.maintenance_provider_discovery_tick()

        records = [
            r for r in orch._merkle.read_all()
            if r.action == "self_maintenance.provider_discovery_tick"
        ]
        assert len(records) == 1
        record = records[0]
        assert record.result == "ran"
        assert "missing" in record.payload
        assert "present" in record.payload
        assert "skipped" in record.payload
        assert record.payload["missing"]


class TestProviderDiscoveryTickIsolatedCycle:
    def test_registered_alongside_provider_smoke_cycle_in_scheduler(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El ciclo debe estar cableado en el scheduler junto a
        `_provider_smoke_cycle` -- mismo mecanismo de aislamiento
        (`_isolated_cycle`), no un mecanismo nuevo. Se verifica indirectamente:
        construir el scheduler no debe fallar y debe incluir un extra_cycle
        adicional respecto al smoke (conteo de extra_cycles)."""
        scheduler = orch.maintenance_scheduler()
        # extra_cycles es una tupla de callables; debe haber al menos 7:
        # dep, batch, self_build, research, provider_smoke, knowledge_ingest,
        # project_graph, provider_discovery (8 tras esta tarea).
        assert len(scheduler._extra_cycles) >= 8
