"""
ADR-033 — Cableado de los refinamientos del loop a las superficies.

Verifica que las cuatro capacidades de ADR-033 son accesibles desde fuera del
Orchestrator:
  - serve: AtlasServiceRunner.tick() barre loops suspendidos expirados.
  - CLI: `atlas approve --only/--abort`, `atlas pending` con mutaciones,
    `atlas sweep`.
  - ops: OrchestratorOps.approve(abort=, approve_only=) + sweep_suspensions.
  - Telegram: on_agentic_progress opt-in; /pending lista mutaciones.
  - Dashboard: /api/agentic/progress feed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.contracts import Event, EventType, Task
from atlas.core.orchestrator import Orchestrator
from atlas.runtime.service_runner import AtlasServiceRunner


# ---------------------------------------------------------------------------
# Dobles reusados de los tests del loop
# ---------------------------------------------------------------------------


class _ScriptedHub:
    def __init__(self, script: list) -> None:  # noqa: ANN001
        self._script = list(script)
        self.calls: list = []

    def infer(self, request):  # noqa: ANN001, ANN201
        self.calls.append(request)
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]


def _resp(text: str = "", tool_calls: list | None = None):  # noqa: ANN001, ANN201
    from atlas.core.inference_hub import InferenceLevel, InferenceResponse

    return InferenceResponse(
        text=text, provider="mock", model="m", level=InferenceLevel.L1,
        latency_ms=1, success=True, tokens_used=1, mode="live",
        tool_calls=tool_calls or [],
    )


class _FakeEditor:
    def __init__(self) -> None:
        self.writes: list = []

    def write_file(self, path, content, clearance=None):  # noqa: ANN001, ANN201
        self.writes.append((str(path), content, clearance))
        return SimpleNamespace(ok=True, path=str(path), bytes_written=len(content))


def _write_call(tc_id: str = "m1", path: str = "f.txt", content: str = "hola") -> dict:
    return {
        "id": tc_id,
        "name": "editor_write",
        "arguments": json.dumps({"path": path, "content": content}),
    }


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    monkeypatch.delenv("ATLAS_AGENTIC_AUTO_APPROVE", raising=False)
    monkeypatch.delenv("ATLAS_AGENTIC_SUSPENSION_TTL", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


def _suspend(orch: Orchestrator) -> Task:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    return orch.handle_intent("escribe algo")


def _age_state(orch: Orchestrator, task: Task, hours: int = 2) -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    task.metadata["agentic_state"]["created_at"] = old
    orch._persist_pending_approval(task)


# ===========================================================================
# serve — tick barre loops expirados
# ===========================================================================


def test_service_runner_tick_sweeps_expired(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_AGENTIC_SUSPENSION_TTL", "3600")
    # Reconstruir para tomar el TTL del entorno.
    o = Orchestrator(workspace=orch._workspace)
    task = _suspend(o)
    _age_state(o, task)

    runner = AtlasServiceRunner(o)
    cancelled = runner.tick(force=True)

    assert task.id in cancelled  # type: ignore[attr-defined]


def test_service_runner_tick_throttled(orch: Orchestrator) -> None:
    runner = AtlasServiceRunner(orch)
    runner._sweep_interval_s = 9999.0
    # Primer tick (force) corre; segundo sin force está throttled → [].
    runner.tick(force=True)
    assert runner.tick(force=False) == []


# ===========================================================================
# CLI — approve --only / sweep / pending con mutaciones
# ===========================================================================


def test_cli_pending_shows_mutations_and_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    import atlas.interfaces.cli as cli_mod

    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.setenv("ATLAS_AGENTIC_SUSPENSION_TTL", "3600")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)

    o = Orchestrator(workspace=tmp_path / "atlas")
    task = _suspend(o)
    _age_state(o, task)

    # La CLI usa get_orchestrator(); inyectamos el nuestro.
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: o)
    runner = CliRunner()

    out = runner.invoke(cli_mod.cli, ["pending"])
    assert out.exit_code == 0
    assert "editor_write" in out.output  # la mutación aparece listada

    swept = runner.invoke(cli_mod.cli, ["sweep"])
    assert swept.exit_code == 0
    assert task.id in swept.output


def test_cli_approve_partial_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    import atlas.interfaces.cli as cli_mod

    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)

    o = Orchestrator(workspace=tmp_path / "atlas")
    editor = _FakeEditor()
    o.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([
        _resp(tool_calls=[
            _write_call(tc_id="a", path="ok.txt", content="si"),
            _write_call(tc_id="b", path="no.txt", content="no"),
        ]),
        _resp(text="hecho"),
    ])
    o.enable_gate_d_pipeline(inference_hub=hub)
    task = o.handle_intent("escribe dos")

    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: o)
    runner = CliRunner()
    res = runner.invoke(cli_mod.cli, ["approve", task.id, "--only", "a"])

    assert res.exit_code == 0
    assert len(editor.writes) == 1  # solo la "a" corrió
    assert editor.writes[0][1] == "si"


# ===========================================================================
# ops — approve kwargs + sweep
# ===========================================================================


def test_ops_approve_kwargs_and_sweep(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atlas.interfaces.orchestrator_ops import OrchestratorOps

    task = _suspend(orch)
    ops = OrchestratorOps(orch)
    # Aprobación parcial sin ids → denegación del lote y reanuda (deny-like via
    # approve_only vacío no; aquí probamos abort).
    res = ops.approve(task.id, False, abort=True)
    assert res["approved"] is False

    # sweep sin TTL configurado → no-op.
    assert ops.sweep_suspensions(ttl_seconds=None) == []


# ===========================================================================
# Telegram — progress opt-in y /pending con mutaciones
# ===========================================================================


def _make_progress_event(task_id: str = "t1") -> Event:
    return Event(
        type=EventType.AGENTIC_PROGRESS,
        payload={"task_id": task_id, "iteration": 2, "tool": "git_log",
                 "summary": "commits reales"},
        task_id=task_id,
    )


def test_telegram_progress_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_telegram_bot import _make_bot

    bot, client, _ = _make_bot()

    # Sin opt-in → silencio.
    monkeypatch.delenv("ATLAS_TELEGRAM_PROGRESS", raising=False)
    bot.on_agentic_progress(_make_progress_event())
    assert client.sent == []

    # Con opt-in → notifica.
    monkeypatch.setenv("ATLAS_TELEGRAM_PROGRESS", "1")
    bot.on_agentic_progress(_make_progress_event())
    assert any("Progreso" in t for _, t in client.sent)


def test_telegram_pending_lists_mutations() -> None:
    from tests.test_telegram_bot import _make_bot

    bot, _, ops = _make_bot()
    ops.pending_approvals = lambda: [{  # type: ignore[assignment]
        "task_id": "t9", "intent": "edita", "reason": "mutación",
        "pending_mutations": [{"id": "a", "name": "editor_write"}],
    }]
    out = bot._cmd_pending("")
    assert "editor_write" in out
    assert "a:editor_write" in out


def test_telegram_approval_keyboard_per_mutation() -> None:
    """Con >1 mutación, el teclado ofrece un botón 'Solo <name>' por mutación
    + Cancelar, todos con callback_data <=64 bytes."""
    from tests.test_telegram_bot import _make_bot

    bot, _, _ = _make_bot()
    payload = {
        "task_id": "t1",
        "pending_mutations": [
            {"id": "a", "name": "editor_write"},
            {"id": "b", "name": "browser_click"},
        ],
    }
    kb = bot._approval_keyboard("t1", payload)
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    cbs = [b["callback_data"] for b in flat]
    assert "approve:t1:only:a" in cbs
    assert "approve:t1:only:b" in cbs
    assert "approve:t1:abort" in cbs
    assert all(len(c.encode("utf-8")) <= 64 for c in cbs)


def test_telegram_callback_partial_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_telegram_bot import _make_bot

    bot, _, ops = _make_bot()
    cb = {
        "id": "cb1", "from": {"id": 42}, "message": {"chat": {"id": 42}},
        "data": "approve:t1:only:a",
    }
    bot.handle_update({"callback_query": cb})
    # Se llamó approve con approve_only=["a"]
    assert ops.approve_kwargs[-1]["approve_only"] == ["a"]
    assert ops.approve_kwargs[-1]["abort"] is False


def test_telegram_callback_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_telegram_bot import _make_bot

    bot, _, ops = _make_bot()
    cb = {
        "id": "cb2", "from": {"id": 42}, "message": {"chat": {"id": 42}},
        "data": "approve:t1:abort",
    }
    bot.handle_update({"callback_query": cb})
    assert ops.approve_kwargs[-1]["abort"] is True


# ===========================================================================
# Dashboard — /api/agentic/progress
# ===========================================================================


def test_dashboard_progress_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")

    import atlas.interfaces.dashboard as dash
    dash._orch = None
    dash._progress_wired = False
    dash._progress_feed.clear()

    o = Orchestrator(workspace=tmp_path / "atlas")
    dash.set_orchestrator(o)

    # Emitir un progreso por el bus → debe aparecer en el feed.
    o._bus.publish(_make_progress_event("tX"))

    client = TestClient(dash.app, raise_server_exceptions=True)
    res = client.get("/api/agentic/progress")
    assert res.status_code == 200
    data = res.json()
    assert data and data[0]["task_id"] == "tX"
    assert data[0]["tool"] == "git_log"
