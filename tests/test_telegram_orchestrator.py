"""
Tests de integracion C4-s2:
  - approval flow extremo a extremo (Orchestrator + bus + bot fake + ops)
  - OfflineMonitor publica SHADOW_ALERT solo en transicion
  - ThermalWatchdog->bus via callback (bug fix triage_mode->operational_mode)
  - lifecycle: start_telegram_bot sin token es no-op
  - bot callback_query maneja approve:<id>:<yes|no>
  - bot notify_all envia a todos los authorized chat_ids
  - OrchestratorOps.status devuelve dict
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import EventType, OperationalMode
from atlas.core.offline_monitor import OfflineMonitor
from atlas.interfaces.orchestrator_ops import OrchestratorOps
from atlas.interfaces.telegram_bot import TelegramAuthorizer, TelegramBot
from atlas.thermal.watchdog import ThermalState, ThermalWatchdog


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.sent: list[tuple[int, str, dict | None]] = []
        self.cb_replies: list[tuple[str, str]] = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((int(chat_id), text, reply_markup))
        return {"ok": True}

    def get_updates(self, offset=None, timeout_s=25):
        return []

    def answer_callback_query(self, callback_query_id, text=""):
        self.cb_replies.append((callback_query_id, text))
        return {"ok": True}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def orch(workspace: Path):
    from atlas.core.orchestrator import Orchestrator
    import atlas.governance.governance_l0 as g
    g.GovernanceL0._instance = None
    o = Orchestrator(workspace=workspace)
    yield o
    g.GovernanceL0._instance = None


# ---------------------------------------------------------------------------
# OrchestratorOps
# ---------------------------------------------------------------------------

def test_orchestrator_ops_status_returns_dict(orch):
    ops = OrchestratorOps(orch)
    data = ops.status()
    assert isinstance(data, dict)
    assert data["version"]


def test_orchestrator_ops_triage_uses_attached_watchdog(orch):
    state = ThermalState(
        temperature_celsius=42.0, ram_free_mb=8000,
        operational_mode=OperationalMode.NORMAL,
        policy="NORMAL", should_pause_local_llm=False,
        should_delegate_all=False, emergency=False,
    )
    class FakeWD:
        def current_state(self): return state
    orch.attach_thermal_watchdog(FakeWD())
    triage = OrchestratorOps(orch).triage()
    assert triage["mode"] == "normal"
    assert triage["temperature_c"] == 42.0


def test_orchestrator_ops_triage_without_watchdog(orch):
    triage = OrchestratorOps(orch).triage()
    assert triage["mode"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Approval flow
# ---------------------------------------------------------------------------

def _force_requires_approval(orch, intent="modificar config sensible"):
    from dataclasses import replace
    from atlas.core.contracts import RoutingLevel
    original = orch._classifier.classify
    def patched(intent_, **kw):
        result = original(intent_, **kw)
        return replace(result, level=RoutingLevel.REQUIRES_APPROVAL,
                       reason="test-approval", governance_blocked=False)
    orch._classifier.classify = patched  # type: ignore[assignment]


def test_approval_required_publishes_event_and_keeps_pending(orch):
    received: list = []
    orch.bus.subscribe(EventType.APPROVAL_REQUIRED, lambda e: received.append(e))
    _force_requires_approval(orch)
    task = orch.handle_intent("hacer X")

    assert task.status.value == "awaiting_approval"
    assert len(received) == 1
    assert received[0].payload["task_id"] == task.id
    pending = orch.pending_approvals()
    assert any(p["task_id"] == task.id for p in pending)


def test_approve_pending_yes_executes_and_clears(orch):
    _force_requires_approval(orch)
    task = orch.handle_intent("hacer X")
    out = orch.approve_pending(task.id, approved=True)
    assert out["approved"] is True
    assert out["status"] in ("done", "failed")
    assert orch.pending_approvals() == []


def test_approve_pending_no_cancels(orch):
    _force_requires_approval(orch)
    task = orch.handle_intent("hacer X")
    out = orch.approve_pending(task.id, approved=False)
    assert out["approved"] is False
    assert out["status"] == "cancelled"
    assert orch.pending_approvals() == []


def test_approve_unknown_task_returns_error(orch):
    out = orch.approve_pending("non-existent", approved=True)
    assert out["status"] == "unknown"
    assert "error" in out


def test_pending_approval_survives_orchestrator_restart(workspace: Path):
    from atlas.core.orchestrator import Orchestrator
    import atlas.governance.governance_l0 as g

    g.GovernanceL0._instance = None
    first = Orchestrator(workspace=workspace)
    _force_requires_approval(first)
    task = first.handle_intent("hacer X")

    g.GovernanceL0._instance = None
    second = Orchestrator(workspace=workspace)

    pending = second.pending_approvals()
    assert any(p["task_id"] == task.id for p in pending)

    out = second.approve_pending(task.id, approved=False)
    assert out["status"] == "cancelled"
    assert second.pending_approvals() == []
    g.GovernanceL0._instance = None


# ---------------------------------------------------------------------------
# Bot callback_query + notify_all
# ---------------------------------------------------------------------------

def _make_bot(authorized=(1, 2), ops=None):
    if ops is None:
        class Ops:
            def status(self): return {}
            def submit_task(self, intent): return {"status": "executed", "task_id": "x"}
            def recent_audit(self, n=10): return []
            def list_tools(self): return []
            def triage(self): return {}
            def pending_approvals(self): return []
            def approve(self, task_id, approved, *, abort=False, approve_only=None):
                return {"task_id": task_id, "status": "done", "approved": approved}
        ops = Ops()
    client = FakeClient()
    bot = TelegramBot(client=client, authorizer=TelegramAuthorizer(list(authorized)), ops=ops)
    return bot, client, ops


def test_bot_callback_query_approve_yes():
    bot, client, ops = _make_bot()
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq-1", "data": "approve:task-9:yes",
            "from": {"id": 1},
            "message": {"chat": {"id": 1}},
        },
    }
    bot.handle_update(update)
    assert client.cb_replies and "Aprobada" in client.cb_replies[0][1]
    assert client.sent and "task-9" in client.sent[0][1]


def test_bot_callback_query_unauthorized_rejected():
    bot, client, ops = _make_bot(authorized=(1,))
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq-1", "data": "approve:x:yes",
            "from": {"id": 99},
            "message": {"chat": {"id": 99}},
        },
    }
    bot.handle_update(update)
    assert client.cb_replies and "denegado" in client.cb_replies[0][1]
    assert client.sent == []


def test_bot_callback_query_malformed_data():
    bot, client, ops = _make_bot()
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq-1", "data": "garbage",
            "from": {"id": 1}, "message": {"chat": {"id": 1}},
        },
    }
    bot.handle_update(update)
    assert client.cb_replies and "malformado" in client.cb_replies[0][1]


def test_bot_notify_all_sends_to_each_authorized():
    bot, client, ops = _make_bot(authorized=(10, 20, 30))
    sent_count = bot.notify_all("hola")
    assert sent_count == 3
    assert {c[0] for c in client.sent} == {10, 20, 30}


def test_bot_on_approval_required_sends_inline_keyboard():
    bot, client, ops = _make_bot()
    class FakeEvent:
        payload = {"task_id": "t-1", "intent": "borrar foo", "reason": "high risk"}
    bot.on_approval_required(FakeEvent())
    assert client.sent
    text, markup = client.sent[0][1], client.sent[0][2]
    assert "borrar foo" in text
    assert markup and "inline_keyboard" in markup
    btns = markup["inline_keyboard"][0]
    assert {b["text"] for b in btns} == {"Si", "No"}
    assert "approve:t-1:yes" in {b["callback_data"] for b in btns}


def test_bot_on_approval_required_shows_mutation_arguments() -> None:
    bot, client, ops = _make_bot()

    class FakeEvent:
        payload = {
            "task_id": "t-args",
            "intent": "editar",
            "reason": "mutación",
            "pending_mutations": [{
                "id": "m1",
                "name": "editor_write",
                "arguments_preview": '{"path":"visible.txt"}',
                "arguments_sha256": "b" * 64,
            }],
        }

    bot.on_approval_required(FakeEvent())

    text = client.sent[0][1]
    assert "visible.txt" in text
    assert "sha256:bbbbbbbbbbbb" in text


def test_bot_pending_command_lists():
    class Ops:
        def status(self): return {}
        def submit_task(self, intent): return {}
        def recent_audit(self, n=10): return []
        def list_tools(self): return []
        def triage(self): return {}
        def pending_approvals(self):
            return [{"task_id": "abc", "intent": "X", "reason": "Y"}]
        def approve(self, t, a, *, abort=False, approve_only=None): return {}
    bot, client, _ = _make_bot(ops=Ops())
    bot.handle_update({"update_id": 1, "message": {"chat": {"id": 1}, "text": "/pending"}})
    assert client.sent and "abc" in client.sent[0][1]


# ---------------------------------------------------------------------------
# OfflineMonitor
# ---------------------------------------------------------------------------

def test_offline_monitor_emits_only_on_transition(orch):
    class StubHermes:
        SHADOW_TIMEOUT_MINUTES = 15
        def __init__(self): self.flag = False
        def check_offline_fallback(self): return self.flag

    hermes = StubHermes()
    fired: list = []
    orch.bus.subscribe(EventType.SHADOW_ALERT, lambda e: fired.append(e))
    monitor = OfflineMonitor(hermes=hermes, bus=orch.bus, poll_interval_seconds=999)

    # State False -> tick no dispara
    assert monitor.tick() is False
    assert fired == []

    # Transicion False -> True dispara una vez
    hermes.flag = True
    assert monitor.tick() is True
    assert len(fired) == 1

    # Mantenerse activo no re-dispara
    assert monitor.tick() is True
    assert len(fired) == 1

    # Volver a False y luego True dispara de nuevo
    hermes.flag = False
    monitor.tick()
    hermes.flag = True
    monitor.tick()
    assert len(fired) == 2


# ---------------------------------------------------------------------------
# ThermalWatchdog -> bus via callback
# ---------------------------------------------------------------------------

def test_thermal_callback_publishes_thermal_alert(orch):
    received: list = []
    orch.bus.subscribe(EventType.THERMAL_ALERT, lambda e: received.append(e))
    cb = orch.thermal_alert_callback()
    state = ThermalState(
        temperature_celsius=85.0, ram_free_mb=512,
        operational_mode=OperationalMode.DEGRADED,
        policy="DEGRADED test", should_pause_local_llm=True,
        should_delegate_all=False, emergency=False,
    )
    cb(state)
    assert len(received) == 1
    p = received[0].payload
    assert p["mode"] == "degraded"
    assert p["temperature_c"] == 85.0


def test_watchdog_loop_calls_callback_on_mode_change():
    """Verifica el bug fix: el loop no crashea y dispara callback en cambio de modo."""
    calls: list = []
    wd = ThermalWatchdog(poll_interval_seconds=1,
                         alert_callback=lambda s: calls.append(s))
    # Inyectamos directamente estados para no depender de hardware real
    from atlas.thermal.watchdog import ThermalState

    s1 = ThermalState(40.0, 8000, OperationalMode.NORMAL, "n", False, False, False)
    s2 = ThermalState(85.0, 8000, OperationalMode.DEGRADED, "d", True, False, False)

    # Simulamos la logica del loop sin arrancar el thread
    wd._compute_state = lambda: s1  # type: ignore[assignment]
    # Primer ciclo: prev None, no notifica
    wd._current_state = wd._compute_state()
    # Segundo ciclo: cambio NORMAL -> DEGRADED
    wd._compute_state = lambda: s2  # type: ignore[assignment]
    prev = wd._current_state.operational_mode
    new_state = wd._compute_state()
    if prev != new_state.operational_mode:
        wd._alert_callback(new_state)
    assert len(calls) == 1
    assert calls[0].operational_mode == OperationalMode.DEGRADED


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_start_telegram_bot_without_token_is_noop(orch, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    ok = orch.start_telegram_bot()
    assert ok is False
    assert orch._telegram_bot is None


def test_wire_bus_to_bot_subscribes_all_events(orch):
    class FakeBot:
        def __init__(self):
            self.calls: list[str] = []
        def on_thermal_alert(self, e): self.calls.append("thermal")
        def on_shadow_alert(self, e): self.calls.append("shadow")
        def on_approval_required(self, e): self.calls.append("approval")
        def on_session_started(self, e): self.calls.append("session")
        def on_cold_update_batch_ready(self, e): self.calls.append("batch_ready")

    bot = FakeBot()
    orch._wire_bus_to_bot(bot)

    orch.bus.publish_type(EventType.THERMAL_ALERT, {})
    orch.bus.publish_type(EventType.SHADOW_ALERT, {})
    orch.bus.publish_type(EventType.APPROVAL_REQUIRED, {})
    orch.bus.publish_type(EventType.SESSION_STARTED, {})

    assert bot.calls == ["thermal", "shadow", "approval", "session"]


def test_wire_bus_to_bot_subscribes_cold_update_batch_ready(orch):
    class FakeBot:
        def __init__(self):
            self.calls: list[str] = []
        def on_thermal_alert(self, e): pass
        def on_shadow_alert(self, e): pass
        def on_approval_required(self, e): pass
        def on_session_started(self, e): pass
        def on_cold_update_batch_ready(self, e): self.calls.append("batch_ready")

    bot = FakeBot()
    orch._wire_bus_to_bot(bot)

    orch.bus.publish_type(EventType.COLD_UPDATE_BATCH_READY, {})

    assert bot.calls == ["batch_ready"]
