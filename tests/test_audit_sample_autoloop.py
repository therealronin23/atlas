"""T5 — audit_sample daemon in-process en AtlasServiceRunner (gated, patrón swarm).

Reglas:
- Gate OFF por defecto → _audit_sample_thread es None.
- Gate ON → hilo arranca, llama swarm_audit_sample, stop() joinea sin colgar.
- Espera troceada (chopped sleep) permite stop rápido.
- CERO red / subprocesos reales: orquestador fake, poll cortísimo por env.
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
    return Orchestrator(workspace=tmp_path / "atlas")


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el subsistema de audit_sample del resto."""
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "ATLAS_PROMETHEUS",
        "ATLAS_SERVE_DASHBOARD",
        "ATLAS_THERMAL_MONITOR",
        "ATLAS_MAINTENANCE_SCHEDULER",
        "ATLAS_SELF_AUDIT_SCHEDULER",
        "ATLAS_SWARM_SCHEDULER",
    ):
        monkeypatch.delenv(var, raising=False)


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestAuditSampleScheduler:
    def test_not_started_by_default(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.delenv("ATLAS_AUDIT_SAMPLE_SCHEDULER", raising=False)
        runner = AtlasServiceRunner(orch)
        runner.start()
        assert runner._audit_sample_thread is None
        runner.stop()

    def test_thread_none_in_init(
        self, orch: Orchestrator
    ) -> None:
        runner = AtlasServiceRunner(orch)
        assert runner._audit_sample_thread is None

    def test_started_and_calls_swarm_audit_sample(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_SCHEDULER", "1")
        # Poll cortísimo para que el test no tarde.
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_POLL_S", "0.1")
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_FRACTION", "0.3")

        calls: list[dict] = []
        invoked = threading.Event()

        def _fake_audit_sample(fraction: float = 0.2) -> dict:
            calls.append({"fraction": fraction})
            invoked.set()
            return {"sampled": 0}

        monkeypatch.setattr(orch, "swarm_audit_sample", _fake_audit_sample)

        runner = AtlasServiceRunner(orch)
        runner.start()
        assert invoked.wait(timeout=3.0), "swarm_audit_sample no fue invocado"
        assert runner._audit_sample_thread is not None
        assert runner._audit_sample_thread.is_alive()
        assert calls[0]["fraction"] == pytest.approx(0.3)

        runner.stop()
        assert not runner._audit_sample_thread.is_alive()

    def test_stop_joins_cleanly(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_SCHEDULER", "1")
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_POLL_S", "0.05")

        started = threading.Event()

        def _fake_audit_sample(fraction: float = 0.2) -> dict:
            started.set()
            return {}

        monkeypatch.setattr(orch, "swarm_audit_sample", _fake_audit_sample)

        runner = AtlasServiceRunner(orch)
        runner.start()
        assert started.wait(timeout=3.0)

        t0 = time.monotonic()
        runner.stop()
        elapsed = time.monotonic() - t0
        # El stop debe ser rápido (poll=0.05s, chunks de 5s → corta en el chunk)
        assert elapsed < 5.0
        assert runner._audit_sample_thread is not None
        assert not runner._audit_sample_thread.is_alive()

    def test_exception_does_not_kill_loop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _base_env(monkeypatch)
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_SCHEDULER", "1")
        monkeypatch.setenv("ATLAS_AUDIT_SAMPLE_POLL_S", "0.05")

        count: dict[str, int] = {"n": 0}
        second_called = threading.Event()

        def _fake_audit_sample(fraction: float = 0.2) -> dict:
            count["n"] += 1
            if count["n"] == 1:
                raise RuntimeError("fallo simulado")
            second_called.set()
            return {}

        monkeypatch.setattr(orch, "swarm_audit_sample", _fake_audit_sample)

        runner = AtlasServiceRunner(orch)
        runner.start()
        assert second_called.wait(timeout=5.0), "bucle murió tras la excepción"
        runner.stop()
        assert not runner._audit_sample_thread.is_alive()
