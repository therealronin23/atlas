"""Gate I — service runner and health report."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.runtime.service_runner import AtlasServiceRunner


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    # ATLAS_CORE_ROOT: sin esto, cualquier extra_cycle real del scheduler
    # (self-build/research/provider-smoke) que se dispare en un test opera
    # sobre el REPO REAL, no tmp_path (incidente 2026-07-09: 13 worktrees
    # git reales + cascada de subprocess pytest — ver test_maintenance_autoloop.py).
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    return Orchestrator(workspace=tmp_path / "atlas")


def test_health_report_fields(orch: Orchestrator) -> None:
    h = orch.health_report()
    assert h["version"] == orch.VERSION
    assert "governance_ok" in h
    assert "merkle_chain_ok" in h
    assert "gate_h" in h
    assert "pending_approvals_count" in h


def test_service_runner_start_stop(orch: Orchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Disable Prometheus/dashboard/thermal so they don't try to bind real ports
    monkeypatch.delenv("ATLAS_PROMETHEUS", raising=False)
    monkeypatch.delenv("ATLAS_SERVE_DASHBOARD", raising=False)
    monkeypatch.delenv("ATLAS_THERMAL_MONITOR", raising=False)
    runner = AtlasServiceRunner(orch)
    runner.start()
    assert runner._running
    assert orch._offline_monitor is not None
    runner.stop()
    assert not runner._running


# ---------------------------------------------------------------------------
# Ventana SIGTERM en run_forever (ATLAS PRIME Cycle 5, 2026-07-22) — start()
# lanza varios threads/servers y puede tardar; si los handlers de señal se
# instalan DESPUÉS de start() (como antes), un SIGTERM/SIGINT llegado durante
# el arranque cae en la acción por defecto del sistema (mata el proceso sin
# pasar por stop(), sin limpieza, sin el log service.stopped).


def test_run_forever_installs_signal_handlers_before_start(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prueba la causa raíz directamente: el orden de instalación, no la
    entrega real de la señal (frágil/no determinista en tests)."""
    import signal

    runner = AtlasServiceRunner(orch)
    call_order: list[str] = []
    monkeypatch.setattr(runner, "start", lambda: call_order.append("start"))
    monkeypatch.setattr(runner, "stop", lambda: call_order.append("stop"))

    original_signal = signal.signal

    def _record_signal(signalnum: int, handler: object) -> object:
        call_order.append(f"signal:{signalnum}")
        return original_signal(signalnum, handler)  # type: ignore[arg-type]

    monkeypatch.setattr(signal, "signal", _record_signal)

    # start() mockeado no toca _running (queda False del __init__): el bucle
    # while no se ejecuta y run_forever vuelve enseguida — sin eso el test
    # colgaría en un bucle infinito.
    runner.run_forever(poll_interval_s=0.001)

    start_index = call_order.index("start")
    signal_indices = [i for i, c in enumerate(call_order) if c.startswith("signal:")]
    assert signal_indices, call_order
    assert all(i < start_index for i in signal_indices), (
        f"las señales deben instalarse ANTES de start(): {call_order}"
    )


def test_stop_cleans_up_even_if_running_flag_was_cleared_before_stop_call(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modela la carrera real: start() fija `_running=True` en mitad de su
    ejecución (linea ~335); si una señal llega justo después y limpia
    `_running` a False ANTES de que `stop()` corra, el guard viejo
    (`if not self._running: return`) trataba eso como 'nunca arrancó' y
    saltaba TODA la limpieza (offline monitor, telegram, log service.stopped
    nunca se escribía) — sin lanzar, sin avisar. `stop()` ahora debe basar el
    guard en que `start()` completó, no en el valor de `_running` en ese
    instante."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ATLAS_PROMETHEUS", raising=False)
    monkeypatch.delenv("ATLAS_SERVE_DASHBOARD", raising=False)
    monkeypatch.delenv("ATLAS_THERMAL_MONITOR", raising=False)
    runner = AtlasServiceRunner(orch)
    runner.start()
    assert orch._offline_monitor is not None
    monitor = orch._offline_monitor

    # Simula la señal llegando justo tras start(), antes de stop().
    runner._running = False

    runner.stop()

    # Si la limpieza real corrió: el orquestador soltó la referencia (stop_offline_monitor
    # la pone a None) y el propio monitor quedó parado de verdad.
    assert orch._offline_monitor is None
    assert monitor._running is False
