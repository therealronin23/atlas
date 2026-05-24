"""
Tests ADR-012 — pull-on-reconnect memory sync Hermes↔Atlas (FU-2).

Cubre:
  - sync_offline_queue() drena entradas pendientes (happy path)
  - sync_offline_queue() marca failed cuando enqueue_task lanza excepcion
  - sync_offline_queue() devuelve resumen {sent, failed, skipped}
  - sync_offline_queue() escribe en Merkle
  - HERMES_RECONNECTED en EventBus dispara sync automatico
  - OfflineMonitor.tick() detecta transicion offline->online y emite HERMES_RECONNECTED
  - Cola vacia retorna zeros sin errores
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.core.contracts import DelegationPayload, EventType
from atlas.core.event_bus import EventBus
from atlas.core.offline_monitor import OfflineMonitor
from atlas.core.orchestrator import Orchestrator
from atlas.hermes.hermes import DelegationBuilder, HermesMockAdapter, OfflineQueue, QueueEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    return Orchestrator(workspace=tmp_path / "atlas")


@pytest.fixture
def queue(tmp_path: Path) -> OfflineQueue:
    return OfflineQueue(store_path=tmp_path)


def _make_payload(priority: int = 3) -> DelegationPayload:
    return DelegationBuilder.build(
        task_id="task-test-123",
        intent="test intent",
        priority=priority,
    )


# ---------------------------------------------------------------------------
# sync_offline_queue — happy path
# ---------------------------------------------------------------------------

class TestSyncOfflineQueueHappyPath:

    def test_empty_queue_returns_zeros(self, orch: Orchestrator) -> None:
        result = orch.sync_offline_queue()
        assert result == {"sent": 0, "failed": 0, "skipped": 0}

    def test_pending_entries_marked_sent(self, orch: Orchestrator) -> None:
        # Pre-poblar la OfflineQueue del orchestrator con 2 entradas
        payload1 = _make_payload(priority=3)
        payload2 = _make_payload(priority=2)
        orch._offline_queue.enqueue(QueueEntry(delegation=payload1))
        orch._offline_queue.enqueue(QueueEntry(delegation=payload2))

        assert orch._offline_queue.depth == 2
        result = orch.sync_offline_queue()

        assert result["sent"] == 2
        assert result["failed"] == 0
        assert result["skipped"] == 0
        # Despues del sync la cola queda vacia (entradas marcadas "sent")
        assert orch._offline_queue.depth == 0

    def test_entries_forwarded_to_hermes(self, orch: Orchestrator) -> None:
        """Los payloads llegan al mock de Hermes tras el sync."""
        payload = _make_payload()
        orch._offline_queue.enqueue(QueueEntry(delegation=payload))

        orch.sync_offline_queue()

        # HermesMockAdapter almacena las tareas en _queue indexado por delegation.id
        queued_ids = [p.task_id for p in orch._hermes_mock._queue.values()]
        assert payload.task_id in queued_ids


# ---------------------------------------------------------------------------
# sync_offline_queue — failures
# ---------------------------------------------------------------------------

class TestSyncOfflineQueueFailures:

    def test_enqueue_failure_marks_entry_failed(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = _make_payload()
        orch._offline_queue.enqueue(QueueEntry(delegation=payload))

        # Parchear enqueue_task para que lance siempre
        monkeypatch.setattr(
            orch._hermes_mock, "enqueue_task",
            lambda _p: (_ for _ in ()).throw(RuntimeError("hermes caído")),
        )

        result = orch.sync_offline_queue()

        assert result["sent"] == 0
        assert result["failed"] == 1
        # La entrada queda con status "failed", no "pending" -> depth sigue 0 pendientes
        assert orch._offline_queue.depth == 0
        failed_entries = [
            e for e in orch._offline_queue._entries if e.status == "failed"
        ]
        assert len(failed_entries) == 1

    def test_partial_failure_summary(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2 pendientes: 1 exito, 1 fallo."""
        p1 = _make_payload(priority=3)
        p2 = _make_payload(priority=3)
        orch._offline_queue.enqueue(QueueEntry(delegation=p1))
        orch._offline_queue.enqueue(QueueEntry(delegation=p2))

        call_count = {"n": 0}
        original_enqueue = orch._hermes_mock.enqueue_task

        def selective_enqueue(payload: DelegationPayload) -> Any:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("fallo en segundo envio")
            return original_enqueue(payload)

        monkeypatch.setattr(orch._hermes_mock, "enqueue_task", selective_enqueue)

        result = orch.sync_offline_queue()
        assert result["sent"] == 1
        assert result["failed"] == 1


# ---------------------------------------------------------------------------
# sync_offline_queue — Merkle log
# ---------------------------------------------------------------------------

class TestSyncOfflineQueueMerkle:

    def test_sync_writes_to_merkle(self, orch: Orchestrator) -> None:
        payload = _make_payload()
        orch._offline_queue.enqueue(QueueEntry(delegation=payload))

        before = len(orch._merkle.tail(100))
        orch.sync_offline_queue()
        after = len(orch._merkle.tail(100))

        assert after > before

    def test_sync_merkle_action_name(self, orch: Orchestrator) -> None:
        orch.sync_offline_queue()
        recent = orch._merkle.tail(5)
        sync_logs = [r for r in recent if r.action == "hermes.sync_offline_queue"]
        assert len(sync_logs) >= 1

    def test_merkle_chain_still_valid_after_sync(self, orch: Orchestrator) -> None:
        payload = _make_payload()
        orch._offline_queue.enqueue(QueueEntry(delegation=payload))
        orch.sync_offline_queue()
        ok, _ = orch._merkle.verify_chain()
        assert ok


# ---------------------------------------------------------------------------
# EventBus HERMES_RECONNECTED -> sync automático
# ---------------------------------------------------------------------------

class TestReconnectEventTriggersSync:

    def test_hermes_reconnected_event_drains_queue(self, orch: Orchestrator) -> None:
        """Publicar HERMES_RECONNECTED dispara sync_offline_queue via suscripcion."""
        payload = _make_payload()
        orch._offline_queue.enqueue(QueueEntry(delegation=payload))
        assert orch._offline_queue.depth == 1

        # Disparar el evento como lo haría OfflineMonitor
        orch._bus.publish_type(EventType.HERMES_RECONNECTED, {
            "note": "test reconnect",
        })

        # El suscriptor (lambda en _init_components) llama sync_offline_queue sincrono
        assert orch._offline_queue.depth == 0

    def test_hermes_reconnected_event_logged_in_merkle(self, orch: Orchestrator) -> None:
        orch._bus.publish_type(EventType.HERMES_RECONNECTED, {
            "note": "manual test",
        })
        recent = orch._merkle.tail(5)
        sync_logs = [r for r in recent if r.action == "hermes.sync_offline_queue"]
        assert len(sync_logs) >= 1


# ---------------------------------------------------------------------------
# OfflineMonitor — transicion offline -> online emite HERMES_RECONNECTED
# ---------------------------------------------------------------------------

class TestOfflineMonitorReconnectTransition:

    def test_tick_online_to_offline_does_not_emit_reconnected(self) -> None:
        """Transicion online->offline emite SHADOW_ALERT, NO HERMES_RECONNECTED."""
        hermes = MagicMock()
        bus = MagicMock()
        monitor = OfflineMonitor(hermes=hermes, bus=bus)
        monitor._last_state = False  # estado previo: online

        hermes.check_offline_fallback.return_value = True  # ahora offline
        monitor.tick()

        published_types = [call.args[0] for call in bus.publish_type.call_args_list]
        assert EventType.SHADOW_ALERT in published_types
        assert EventType.HERMES_RECONNECTED not in published_types

    def test_tick_offline_to_online_emits_hermes_reconnected(self) -> None:
        """Transicion offline->online emite HERMES_RECONNECTED."""
        hermes = MagicMock()
        bus = MagicMock()
        monitor = OfflineMonitor(hermes=hermes, bus=bus)
        monitor._last_state = True  # estado previo: offline

        hermes.check_offline_fallback.return_value = False  # ahora online
        monitor.tick()

        published_types = [call.args[0] for call in bus.publish_type.call_args_list]
        assert EventType.HERMES_RECONNECTED in published_types
        assert EventType.SHADOW_ALERT not in published_types

    def test_tick_stable_offline_emits_nothing(self) -> None:
        """Sin transicion (offline->offline) no emite ningun evento."""
        hermes = MagicMock()
        bus = MagicMock()
        monitor = OfflineMonitor(hermes=hermes, bus=bus)
        monitor._last_state = True  # previo: offline

        hermes.check_offline_fallback.return_value = True  # sigue offline
        monitor.tick()

        bus.publish_type.assert_not_called()

    def test_tick_reconnect_payload_has_note(self) -> None:
        """El payload de HERMES_RECONNECTED incluye 'note'."""
        hermes = MagicMock()
        bus = MagicMock()
        monitor = OfflineMonitor(hermes=hermes, bus=bus)
        monitor._last_state = True

        hermes.check_offline_fallback.return_value = False
        monitor.tick()

        call_args = bus.publish_type.call_args
        assert call_args is not None
        event_type, payload = call_args.args
        assert event_type == EventType.HERMES_RECONNECTED
        assert "note" in payload

    def test_tick_updates_last_state_after_reconnect(self) -> None:
        """Tras la transicion offline->online, _last_state queda False."""
        hermes = MagicMock()
        bus = MagicMock()
        monitor = OfflineMonitor(hermes=hermes, bus=bus)
        monitor._last_state = True

        hermes.check_offline_fallback.return_value = False
        monitor.tick()

        assert monitor._last_state is False
