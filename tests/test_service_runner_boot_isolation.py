"""El arranque del daemon aísla fallos por subsistema; el apagado ya lo hacía.

`AtlasServiceRunner.stop()` lleva desde siempre el idioma defensivo ("la parada
no debe romper el shutdown"). `start()` no lo tenía: encadenaba nueve arranques
opcionales y CUALQUIERA que lanzara mataba el proceso entero — incluido el lazo
de autoconstrucción, que ni siquiera es el que falló.

Eso es lo que convirtió un puerto ocupado en 4.872 reinicios el 2026-08-02.

Dos invariantes, y son opuestas a propósito:
  1. Un accesorio caído NO tumba el runtime.
  2. Un accesorio caído NO se calla: queda en `degraded_subsystems` y en el
     ledger Merkle. La parada silenciosa es el modo de fallo que ya costó
     24 días de lazo apagado y 23 h de daemon muerto sin que nadie lo supiera.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from atlas.runtime.service_runner import AtlasServiceRunner


class _FakeMerkle:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def log(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


def _fake_orchestrator() -> SimpleNamespace:
    return SimpleNamespace(
        VERSION="test",
        _merkle=_FakeMerkle(),
        _thermal_watchdog=None,
        _maintenance_scheduler=None,
        start_offline_monitor=lambda **_: None,
        stop_offline_monitor=lambda: None,
        start_telegram_bot=lambda: False,
        stop_telegram_bot=lambda: None,
    )


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> AtlasServiceRunner:
    """Runner con todos los arranques opcionales neutralizados salvo el que
    cada test decida romper."""
    r = AtlasServiceRunner(_fake_orchestrator())  # type: ignore[arg-type]
    for stage in (
        "_wire_operational_alerts",
        "_start_thermal_if_enabled",
        "_start_dashboard_if_enabled",
        "_start_prometheus_if_enabled",
        "_start_maintenance_scheduler_if_enabled",
        "_start_self_audit_scheduler_if_enabled",
        "_start_swarm_scheduler_if_enabled",
        "_start_audit_sample_scheduler_if_enabled",
        "_start_knowledge_scheduler_if_enabled",
    ):
        monkeypatch.setattr(r, stage, lambda: None)
    return r


def test_arranque_limpio_no_declara_degradacion(runner: AtlasServiceRunner) -> None:
    runner.start()

    assert runner._started is True
    assert runner.degraded_subsystems == {}


def test_un_accesorio_que_lanza_no_tumba_el_arranque(
    runner: AtlasServiceRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso del 02-ago: el exportador lanza y el daemon TIENE que seguir."""

    def _revienta() -> None:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(runner, "_start_prometheus_if_enabled", _revienta)

    runner.start()  # antes: OSError -> proceso muerto -> systemd -> repetir

    assert runner._started is True
    assert runner._running is True


def test_el_accesorio_caido_queda_declarado(
    runner: AtlasServiceRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degradar en silencio sería cambiar un fallo ruidoso por uno invisible."""

    def _revienta() -> None:
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(runner, "_start_prometheus_if_enabled", _revienta)

    runner.start()

    degradados = runner.degraded_subsystems
    assert "prometheus" in degradados
    assert "Address already in use" in degradados["prometheus"]

    acciones = [e["action"] for e in runner._orch._merkle.entries]
    assert "service.subsystem_degraded" in acciones
    degradado = next(
        e for e in runner._orch._merkle.entries
        if e["action"] == "service.subsystem_degraded"
    )
    assert degradado["payload"]["subsystem"] == "prometheus"
    assert degradado["result"] == "degraded"


def test_un_fallo_no_cancela_los_subsistemas_posteriores(
    runner: AtlasServiceRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El orden importaba: prometheus va ANTES que el scheduler de
    mantenimiento, o sea que el lazo de autoconstrucción moría por un puerto."""
    arrancados: list[str] = []

    def _revienta() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "_start_prometheus_if_enabled", _revienta)
    monkeypatch.setattr(
        runner, "_start_maintenance_scheduler_if_enabled",
        lambda: arrancados.append("maintenance"),
    )
    monkeypatch.setattr(
        runner, "_start_knowledge_scheduler_if_enabled",
        lambda: arrancados.append("knowledge"),
    )

    runner.start()

    assert arrancados == ["maintenance", "knowledge"]


def test_varios_fallos_se_acumulan(
    runner: AtlasServiceRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _revienta() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "_start_prometheus_if_enabled", _revienta)
    monkeypatch.setattr(runner, "_start_dashboard_if_enabled", _revienta)

    runner.start()

    assert set(runner.degraded_subsystems) == {"prometheus", "dashboard"}
    assert runner._started is True


def test_service_started_declara_cuantos_degradaron(
    runner: AtlasServiceRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`service.started` con result=success mientras dos subsistemas están
    muertos es exactamente la mentira que hay que evitar."""

    def _revienta() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "_start_prometheus_if_enabled", _revienta)

    runner.start()

    started = next(
        e for e in runner._orch._merkle.entries if e["action"] == "service.started"
    )
    assert started["payload"]["degraded"] == ["prometheus"]
    assert started["result"] == "degraded"
