"""
Gate I — AtlasServiceRunner: proceso 24/7 con Telegram, OfflineMonitor y alertas.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Any

from atlas.core.contracts import Event, EventType
from atlas.core.orchestrator import Orchestrator

_log = logging.getLogger(__name__)


class AtlasServiceRunner:
    """Supervisa subsistemas de larga duracion; no ejecuta tareas por si solo."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator
        self._running = False
        self._dashboard_thread: threading.Thread | None = None

    def _wire_operational_alerts(self) -> None:
        def _on_alert(event: Event) -> None:
            self._orch._merkle.log(
                action="service.alert",
                agent="service_runner",
                result="notified",
                risk_level="moderate",
                payload={
                    "event_type": event.type.value,
                    "summary": event.payload,
                },
                task_id=event.task_id,
            )
        for etype in (
            EventType.SHADOW_ALERT,
            EventType.THERMAL_ALERT,
            EventType.HERMES_RECONNECTED,
        ):
            self._orch.bus.subscribe(etype, _on_alert)

    def _start_thermal_if_enabled(self) -> None:
        if os.environ.get("ATLAS_THERMAL_MONITOR", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        from atlas.thermal.watchdog import ThermalWatchdog

        watchdog = ThermalWatchdog(alert_callback=self._orch.thermal_alert_callback())
        watchdog.start()
        self._orch.attach_thermal_watchdog(watchdog)
        _log.info("ThermalWatchdog activo")

    def _start_dashboard_if_enabled(self) -> None:
        if os.environ.get("ATLAS_SERVE_DASHBOARD", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        from atlas.interfaces.dashboard import serve

        host = os.environ.get("ATLAS_DASHBOARD_HOST", "127.0.0.1")
        port = int(os.environ.get("ATLAS_DASHBOARD_PORT", "7331"))

        def _run() -> None:
            serve(host=host, port=port)

        self._dashboard_thread = threading.Thread(
            target=_run,
            daemon=True,
            name="atlas-dashboard",
        )
        self._dashboard_thread.start()
        _log.info("Dashboard en http://%s:%s", host, port)

    def start(self) -> None:
        self._wire_operational_alerts()
        self._orch.start_offline_monitor(
            poll_interval_seconds=int(os.environ.get("ATLAS_OFFLINE_POLL_S", "60")),
        )
        if self._orch.start_telegram_bot():
            _log.info("Telegram bot iniciado")
        else:
            _log.info("Telegram bot no iniciado (sin token)")
        self._start_thermal_if_enabled()
        self._start_dashboard_if_enabled()
        self._running = True
        self._orch._merkle.log(
            action="service.started",
            agent="service_runner",
            result="success",
            risk_level="safe",
            payload={"version": self._orch.VERSION},
        )

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._orch.stop_telegram_bot()
        self._orch.stop_offline_monitor()
        if self._orch._thermal_watchdog is not None:
            self._orch._thermal_watchdog.stop()
        self._orch._merkle.log(
            action="service.stopped",
            agent="service_runner",
            result="success",
            risk_level="safe",
            payload={},
        )

    def run_forever(self, poll_interval_s: float = 1.0) -> None:
        self.start()

        def _handle_sig(_signum: int, _frame: Any) -> None:
            _log.info("Senal de parada recibida")
            self._running = False

        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)

        try:
            while self._running:
                time.sleep(poll_interval_s)
        finally:
            self.stop()
