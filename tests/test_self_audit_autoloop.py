"""ADR-040 — self-audit 24h cableado DENTRO del proceso serve.

Reglas que estos tests fijan:

- **Arranque gateado por env:** el ``AtlasServiceRunner`` solo arranca el bucle de
  self-audit cuando ``ATLAS_SELF_AUDIT_SCHEDULER=1``; por defecto no.
- **Único escritor:** el bucle usa el ``SelfAuditRunner`` del orquestador (mismo
  ``MerkleLogger``) — no hay segundo proceso escritor.
- **Passthrough de cadencia:** ``ATLAS_SELF_AUDIT_HOURS`` /
  ``ATLAS_SELF_AUDIT_INTERVAL_MIN`` llegan a ``run()``.
- **Rearme:** cuando un run termina, el bucle lanza otro mientras el servicio viva.
- **Stop limpio:** ``runner.stop()`` al parar el servicio; el hilo se une.
- **CERO red/LLM/subproceso real:** ``run`` se reemplaza por un fake.
"""

from __future__ import annotations

import threading
import time
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


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el subsistema de self-audit del resto."""
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "ATLAS_PROMETHEUS",
        "ATLAS_SERVE_DASHBOARD",
        "ATLAS_THERMAL_MONITOR",
        "ATLAS_MAINTENANCE_SCHEDULER",
    ):
        monkeypatch.delenv(var, raising=False)


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestSelfAuditScheduler:
    def test_not_started_by_default(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.delenv("ATLAS_SELF_AUDIT_SCHEDULER", raising=False)
        runner = AtlasServiceRunner(orch)
        runner.start()
        assert runner._self_audit_thread is None
        runner.stop()

    def test_started_and_uses_orchestrator_runner(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_SELF_AUDIT_SCHEDULER", "1")
        monkeypatch.setenv("ATLAS_SELF_AUDIT_HOURS", "12")
        monkeypatch.setenv("ATLAS_SELF_AUDIT_INTERVAL_MIN", "30")

        audit = orch.self_audit()  # construye el runner real (único escritor)
        calls: list[dict] = []
        started = threading.Event()

        def _fake_run(**kwargs):
            calls.append(kwargs)
            started.set()
            # Bloquea hasta que el servicio pida parar (simula un run largo).
            while not audit.stop_requested():
                time.sleep(0.01)
            return None

        monkeypatch.setattr(audit, "run", _fake_run)

        runner = AtlasServiceRunner(orch)
        runner.start()
        assert started.wait(timeout=3.0)
        assert runner._self_audit_thread is not None
        assert runner._self_audit_thread.is_alive()
        # Cadencia desde el entorno
        assert calls[0]["hours"] == 12.0
        assert calls[0]["cycle_interval_minutes"] == 30.0

        runner.stop()
        assert not runner._self_audit_thread.is_alive()

    def test_rearms_after_a_run_finishes(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_SELF_AUDIT_SCHEDULER", "1")

        audit = orch.self_audit()
        count = {"n": 0}

        def _fake_run(**kwargs):
            count["n"] += 1
            if count["n"] >= 2:
                # El segundo run bloquea hasta el stop (evita hot-loop infinito).
                while not audit.stop_requested():
                    time.sleep(0.01)
            return None  # el primer run "termina" → el bucle debe rearmar

        monkeypatch.setattr(audit, "run", _fake_run)

        runner = AtlasServiceRunner(orch)
        runner.start()
        assert _wait_until(lambda: count["n"] >= 2)  # rearmó
        runner.stop()
        assert not runner._self_audit_thread.is_alive()

    def test_run_exception_does_not_kill_loop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_SELF_AUDIT_SCHEDULER", "1")
        # Sleep de backoff cortísimo para no bloquear el test.
        monkeypatch.setenv("ATLAS_SELF_AUDIT_INTERVAL_MIN", "0.0001")

        audit = orch.self_audit()
        count = {"n": 0}

        def _fake_run(**kwargs):
            count["n"] += 1
            if count["n"] == 1:
                raise RuntimeError("revienta el primer run")
            while not audit.stop_requested():
                time.sleep(0.01)
            return None

        monkeypatch.setattr(audit, "run", _fake_run)

        runner = AtlasServiceRunner(orch)
        runner.start()
        # Tras la excepción del 1er run, el bucle sigue vivo y reintenta.
        assert _wait_until(lambda: count["n"] >= 2)
        runner.stop()
        assert not runner._self_audit_thread.is_alive()
