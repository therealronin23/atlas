"""maintenance_mcp_reseed_tick (A.2, ADR-076) — re-siembra continua del
catálogo desde el registro oficial MCP, autolimitada (el registro no cambia
minuto a minuto: el scheduler corre TODOS los extra_cycles a la misma
cadencia global, así que este tick debe saber por su cuenta si ya sembró
recientemente -- workspace/mcp/reseed_state.json, mismo patrón que
f26_gate_state.json).

Esqueleto calcado de tests/test_sentinel_revet_tick.py. El fetcher real
(``atlas.knowledge.sources._urllib_fetcher``) se parchea -- es el único punto
donde ``RegistrySource()`` sin fetcher inyectado toca red -- para que la
suite nunca golpee red real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    monkeypatch.delenv("ATLAS_MCP_RESEED", raising=False)
    monkeypatch.delenv("ATLAS_MCP_RESEED_INTERVAL_S", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "atlas").mkdir(parents=True)
    (tmp_path / "core").mkdir(parents=True)
    return Orchestrator(workspace=tmp_path / "atlas")


def _page(names: list[str]) -> str:
    servers = [{"server": {"name": n, "description": "x"}} for n in names]
    return json.dumps({"servers": servers, "metadata": {}})


def _install_stub_fetcher(monkeypatch: pytest.MonkeyPatch, names: list[str]):
    """Parchea el fetcher real de stdlib -- único punto de red de
    ``RegistrySource()`` sin fetcher inyectado -- por uno que cuenta llamadas
    y nunca toca la red."""
    calls = {"n": 0}
    payload = _page(names)

    def stub(method, url, body, headers):
        calls["n"] += 1
        return 200, payload

    monkeypatch.setattr("atlas.knowledge.sources._urllib_fetcher", stub)
    return calls


def test_disabled_without_env_flag(orch: Orchestrator) -> None:
    assert orch.maintenance_mcp_reseed_tick() == {"status": "disabled"}


def test_nested_run_guard_beats_enable_flag(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    assert orch.maintenance_mcp_reseed_tick() == {"status": "nested_run_guard"}


def test_first_run_reseeds_and_writes_catalog(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")
    _install_stub_fetcher(monkeypatch, ["a", "b"])

    result = orch.maintenance_mcp_reseed_tick()
    assert result["status"] == "ran"
    assert result["candidate_count"] == 2

    catalog_path = Path(orch._maintenance_facade._project_root()) / "docs" / "design" / "mcp_catalog_seeded.yaml"
    doc = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    entries = doc["sectors"]["uncategorized"]["entries"]
    assert {e["name"] for e in entries} == {"a", "b"}


def test_skips_if_last_run_was_recent(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")
    calls = _install_stub_fetcher(monkeypatch, ["a"])

    first = orch.maintenance_mcp_reseed_tick()
    assert first["status"] == "ran"
    calls_after_first = calls["n"]
    assert calls_after_first >= 1

    second = orch.maintenance_mcp_reseed_tick()
    assert second["status"] == "skipped_too_soon"
    assert calls["n"] == calls_after_first  # el fetcher NUNCA se volvió a llamar


def test_reseeds_again_after_interval_elapsed(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")
    monkeypatch.setenv("ATLAS_MCP_RESEED_INTERVAL_S", "0")  # sin ventana -- siempre re-siembra
    _install_stub_fetcher(monkeypatch, ["a"])

    first = orch.maintenance_mcp_reseed_tick()
    second = orch.maintenance_mcp_reseed_tick()
    assert first["status"] == "ran"
    assert second["status"] == "ran"


def test_first_run_without_prior_state_does_not_fail(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin fichero de estado previo (arranque en frío) el tick corre igual --
    no debe interpretarse como 'demasiado pronto'."""
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")
    state_path = Path(orch._maintenance_facade._project_root()) / "workspace" / "mcp" / "reseed_state.json"
    assert not state_path.exists()
    _install_stub_fetcher(monkeypatch, ["a"])

    result = orch.maintenance_mcp_reseed_tick()
    assert result["status"] == "ran"
    assert state_path.exists()


def test_network_failure_reported_honestly_not_silent(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La primera página del registro falla (500) -> reseed_candidates()
    levanta RuntimeError. El tick nunca debe reventar el ciclo del scheduler
    (aislado por _isolated_cycle en el wiring), pero llamado directo debe
    reportar el fallo honesto, no fingir 'ran' con cero candidatos."""
    monkeypatch.setenv("ATLAS_MCP_RESEED", "1")

    def failing_fetcher(method, url, body, headers):
        return 500, "error"

    monkeypatch.setattr("atlas.knowledge.sources._urllib_fetcher", failing_fetcher)

    result = orch.maintenance_mcp_reseed_tick()
    assert result["status"] == "error"

    # Un fallo no cuenta como éxito -- el próximo tick debe poder reintentar
    # de inmediato, no esperar el intervalo completo.
    state_path = Path(orch._maintenance_facade._project_root()) / "workspace" / "mcp" / "reseed_state.json"
    assert not state_path.exists() or json.loads(state_path.read_text()).get("last_success") is None
