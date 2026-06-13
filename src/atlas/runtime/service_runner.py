"""
Gate I — AtlasServiceRunner: proceso 24/7 con Telegram, OfflineMonitor y alertas.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Any  # noqa: TC003 — runtime prometheus handle

from atlas.core.contracts import Event, EventType
from atlas.core.orchestrator import Orchestrator

_log = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class AtlasServiceRunner:
    """Supervisa subsistemas de larga duracion; no ejecuta tareas por si solo."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator
        self._running = False
        self._dashboard_thread: threading.Thread | None = None
        self._self_audit_thread: threading.Thread | None = None
        # ADR-033 #1: barrido periódico de loops agénticos suspendidos y
        # abandonados. Throttled por ATLAS_AGENTIC_SWEEP_S (default 300s). El
        # barrido es no-op salvo que ATLAS_AGENTIC_SUSPENSION_TTL esté fijado,
        # así que es seguro llamarlo aunque la feature esté desactivada.
        try:
            self._sweep_interval_s = float(
                os.environ.get("ATLAS_AGENTIC_SWEEP_S", "300")
            )
        except ValueError:
            self._sweep_interval_s = 300.0
        self._last_sweep_at = 0.0

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

    def _start_maintenance_scheduler_if_enabled(self) -> None:
        """ADR-039 — cron de auto-mantenimiento (off por defecto).

        Activar con ``ATLAS_MAINTENANCE_SCHEDULER=1``. Descubre/analiza/propone y
        enruta cada propuesta corroborada al seam del decisor (ADR-040): bajo
        ``HumanDecider`` (default) nada se adopta — solo se surfa el evento; bajo
        autónomo/híbrido adopta lo reversible. La cadencia es ``ATLAS_MAINTENANCE_POLL_S``
        (default 24h)."""
        if os.environ.get("ATLAS_MAINTENANCE_SCHEDULER", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        scheduler = self._orch.maintenance_scheduler()
        poll = os.environ.get("ATLAS_MAINTENANCE_POLL_S")
        if poll:
            try:
                scheduler._poll_interval = float(poll)
            except ValueError:
                pass
        scheduler.start()
        _log.info("MaintenanceScheduler activo (cron auto-mantenimiento)")

    def _start_self_audit_scheduler_if_enabled(self) -> None:
        """ADR-040 — bucle de self-audit 24h DENTRO del proceso serve.

        El self-audit nació como one-shot del CLI (`atlas self-audit run`), que es
        un escritor SEPARADO: corriéndolo junto al servicio vivo dos `MerkleLogger`
        escriben la misma cadena → carrera → corrupción (el `chain.repaired` del
        29-may). Cableado aquí usa el `MerkleLogger` del orquestador (único
        escritor) → la colisión es imposible por construcción, igual que el
        `MaintenanceScheduler`. Diagnostica sobre el estado vivo; nada se hot-patch
        (los candidatos bajan por ColdUpdate, que valida en worktree aislado).

        Activar con ``ATLAS_SELF_AUDIT_SCHEDULER=1``. Cada run dura
        ``ATLAS_SELF_AUDIT_HOURS`` (default 24) con ciclos cada
        ``ATLAS_SELF_AUDIT_INTERVAL_MIN`` (default 60); al terminar se **rearma**
        (auditoría perpetua, no one-shot). ``Restart=always`` la resucita tras
        reinicios."""
        if os.environ.get("ATLAS_SELF_AUDIT_SCHEDULER", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        self._self_audit_thread = threading.Thread(
            target=self._self_audit_loop,
            daemon=True,
            name="atlas-self-audit",
        )
        self._self_audit_thread.start()
        _log.info("Self-audit scheduler activo (bucle 24h in-process)")

    def _self_audit_loop(self) -> None:
        hours = _env_float("ATLAS_SELF_AUDIT_HOURS", 24.0)
        interval_min = _env_float("ATLAS_SELF_AUDIT_INTERVAL_MIN", 60.0)
        runner = self._orch.self_audit()
        while self._running:
            try:
                runner.run(
                    hours=hours,
                    profile=os.environ.get("ATLAS_SELF_AUDIT_PROFILE", "full"),
                    cycle_interval_minutes=interval_min,
                )
            except Exception:  # noqa: BLE001 — un run caído no mata el bucle ni el servicio
                _log.exception("self-audit run falló; reintenta tras el intervalo")
                # Evita hot-loop si run() revienta al instante.
                time.sleep(min(interval_min * 60.0, 300.0))
            # Al volver (completed/stopped) rearma mientras el servicio viva. Si
            # se paró por stop() (stop_requested), el siguiente run() limpia el
            # flag; pero si fue stop del servicio, _running ya es False y salimos.

    def _start_prometheus_if_enabled(self) -> None:
        if os.environ.get("ATLAS_PROMETHEUS", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        from atlas.monitoring.prometheus_exporter import PrometheusExporter

        port = int(os.environ.get("ATLAS_PROMETHEUS_PORT", "9091"))
        host = os.environ.get("ATLAS_PROMETHEUS_HOST", "127.0.0.1")
        self._prometheus = PrometheusExporter(
            self._orch._observability.telemetry,
            host=host,
            port=port,
        )
        self._prometheus.start()
        _log.info("Prometheus metrics en http://%s:%s/metrics", host, port)

    def _start_dashboard_if_enabled(self) -> None:
        if os.environ.get("ATLAS_SERVE_DASHBOARD", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        from atlas.interfaces.dashboard import serve, set_orchestrator

        # Inject the runtime's Orchestrator so the dashboard does NOT spawn its
        # own (which would corrupt the Merkle chain via dual writers).
        set_orchestrator(self._orch)

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
        self._start_prometheus_if_enabled()
        self._start_maintenance_scheduler_if_enabled()
        self._running = True
        self._start_self_audit_scheduler_if_enabled()
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
        if getattr(self, "_prometheus", None) is not None:
            self._prometheus.stop()
        sched = self._orch._maintenance_scheduler
        if sched is not None and getattr(sched, "_running", False):
            sched.stop()
        if self._self_audit_thread is not None and self._self_audit_thread.is_alive():
            # `_running` ya es False arriba; pedir stop hace que el run() en curso
            # corte en el siguiente chequeo de ciclo y el bucle salga.
            try:
                self._orch.self_audit().stop()
            except Exception:  # noqa: BLE001 — la parada no debe romper el shutdown
                _log.exception("fallo al pedir stop del self-audit")
            self._self_audit_thread.join(timeout=5)
        self._orch._merkle.log(
            action="service.stopped",
            agent="service_runner",
            result="success",
            risk_level="safe",
            payload={},
        )

    def tick(self, *, force: bool = False) -> list[str]:
        """ADR-033: trabajo periódico del loop principal. Hoy: barrer loops
        agénticos suspendidos cuyo TTL expiró. Throttled por
        `_sweep_interval_s`; `force=True` lo salta (útil en tests). Devuelve los
        task_id cancelados (vacío si no toca barrer o no hay nada que barrer)."""
        now = time.monotonic()
        if not force and (now - self._last_sweep_at) < self._sweep_interval_s:
            return []
        self._last_sweep_at = now
        cancelled = self._orch.sweep_expired_suspensions()
        if cancelled:
            _log.info("Barrido TTL: %d loop(s) suspendido(s) cancelado(s)", len(cancelled))
        return cancelled

    def run_forever(self, poll_interval_s: float = 1.0) -> None:
        self.start()

        def _handle_sig(_signum: int, _frame: Any) -> None:
            _log.info("Senal de parada recibida")
            self._running = False

        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)

        try:
            while self._running:
                self.tick()
                time.sleep(poll_interval_s)
        finally:
            self.stop()
