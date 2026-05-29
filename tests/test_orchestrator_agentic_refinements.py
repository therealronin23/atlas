"""
ADR-033 — Refinamientos del loop agéntico suspendible.

Sobre la base de ADR-032 (loop suspendible + HITL inline), este módulo cubre
los cuatro refinamientos que ADR-032 dejó fuera de MVP:

  - #1 sweep_expired_suspensions: barrido opt-in de loops abandonados (TTL).
  - #2 auto-approve allowlist: mutaciones de bajo riesgo corren inline, salvo
       sensibilidad alta. Vacía por defecto (seguro).
  - #3 aprobación parcial: approve_only ejecuta un subconjunto del lote; el
       resto recibe denegación sintética y el loop reanuda.
  - #4 EventType.AGENTIC_PROGRESS: traza por iteración para dashboard/Telegram.

Invariantes que se verifican intactas: clearance siempre concedido antes de
mutar, y toda mutación auto-aprobada queda auditada (task.auto_approved).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.contracts import (
    EventType,
    Task,
    TaskSource,
    TaskStatus,
)
from atlas.core.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Dobles de prueba (espejo de test_orchestrator_mutating_loop.py)
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
        self.writes: list[tuple[str, str, str | None]] = []

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


# ===========================================================================
# #2 Auto-aprobación por allowlist
# ===========================================================================


def test_auto_approved_mutation_runs_inline(orch: Orchestrator) -> None:
    """editor_write en la allowlist + tarea de baja sensibilidad → corre inline
    sin suspender. El loop llega a respuesta final en un único handle_intent."""
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    orch.set_agentic_auto_approve(["editor_write"])
    hub = _ScriptedHub([
        _resp(tool_calls=[_write_call(content="auto")]),
        _resp(text="Hecho sin pedir permiso."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo de confianza")

    assert task.status == TaskStatus.DONE
    assert "agentic_state" not in task.metadata
    assert orch.pending_approvals() == []
    # La mutación corrió, con clearance concedido al vuelo
    assert len(editor.writes) == 1
    _, content, clearance = editor.writes[0]
    assert content == "auto"
    assert clearance == f"task:{task.id}"
    # Hubo reanudación inline: 2 inferencias, no 1
    assert len(hub.calls) == 2


def test_auto_approve_blocked_for_high_sensitivity(orch: Orchestrator) -> None:
    """Aunque la tool esté en la allowlist, sensibilidad alta nunca se salta el
    humano. Unit test directo del predicado."""
    orch.set_agentic_auto_approve(["editor_write"])
    low = Task(intent="x", source=TaskSource.CLI, sensitivity="low")
    high = Task(intent="x", source=TaskSource.CLI, sensitivity="high")

    assert orch._is_agentic_auto_approved("editor_write", low) is True
    assert orch._is_agentic_auto_approved("editor_write", high) is False
    # Fuera de la allowlist → siempre False
    assert orch._is_agentic_auto_approved("browser_click", low) is False


def test_empty_allowlist_still_suspends(orch: Orchestrator) -> None:
    """Seguro por defecto: sin allowlist, toda mutación suspende (compat ADR-032)."""
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo")

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert editor.writes == []
    assert "agentic_state" in task.metadata


def test_env_configures_auto_approve_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ATLAS_AGENTIC_AUTO_APPROVE puebla la allowlist al construir el orchestrator."""
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.setenv("ATLAS_AGENTIC_AUTO_APPROVE", "editor_write, browser_fill ,")
    o = Orchestrator(workspace=tmp_path / "atlas")
    assert o._agentic_auto_approve == frozenset({"editor_write", "browser_fill"})


def test_auto_approved_mutation_audited_in_merkle(orch: Orchestrator) -> None:
    """Una mutación auto-aprobada nunca es silenciosa: task.auto_approved en la
    cadena, con la mutación como tool.invoked, y la cadena íntegra."""
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    orch.set_agentic_auto_approve(["editor_write"])
    hub = _ScriptedHub([
        _resp(tool_calls=[_write_call()]),
        _resp(text="Listo."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe auditado")

    recent = orch._merkle.tail(60)
    actions = {r.action for r in recent if r.task_id == task.id}
    assert "task.auto_approved" in actions
    assert any(
        r.action == "tool.invoked" and r.payload.get("tool") == "editor_write"
        for r in recent
    )
    ok, msg = orch._merkle.verify_chain()
    assert ok, msg


# ===========================================================================
# #3 Aprobación parcial
# ===========================================================================


def test_partial_approval_executes_only_selected(orch: Orchestrator) -> None:
    """Un turno con dos mutaciones; approve_only deja pasar una y deniega la otra.
    El loop reanuda: la aprobada corre, la denegada recibe presión sintética."""
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([
        _resp(tool_calls=[
            _write_call(tc_id="a", path="ok.txt", content="si"),
            _write_call(tc_id="b", path="no.txt", content="no"),
        ]),
        _resp(text="Una hecha, otra denegada."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe dos archivos")
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert len(task.metadata["agentic_state"]["pending_mutations"]) == 2

    res = orch.approve_pending(task.id, True, approve_only=["a"])

    assert res["status"] == "done"
    assert task.status == TaskStatus.DONE
    # Solo la mutación "a" corrió
    assert len(editor.writes) == 1
    assert editor.writes[0][1] == "si"
    # El modelo recibió denegación sintética para "b"
    tool_msgs = [m for m in hub.calls[1].messages if m["role"] == "tool"]
    assert any("denied" in m["content"] and "human_partial" in m["content"]
               for m in tool_msgs)


# ===========================================================================
# #1 Barrido de loops suspendidos abandonados (TTL)
# ===========================================================================


def test_sweep_expired_suspension_cancels_loop(orch: Orchestrator) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo y olvídate")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    # Envejecer el created_at del estado por debajo del TTL, en memoria y disco.
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    task.metadata["agentic_state"]["created_at"] = old
    orch._persist_pending_approval(task)

    cancelled = orch.sweep_expired_suspensions(ttl_seconds=3600)

    assert task.id in cancelled
    assert task.status == TaskStatus.CANCELLED
    assert editor.writes == []
    assert not (orch._pending_approval_dir / f"{task.id}.json").exists()
    # Auditado
    recent = orch._merkle.tail(40)
    assert any(
        r.action == "task.suspension_expired" and r.task_id == task.id
        for r in recent
    )


def test_sweep_noop_when_ttl_disabled(orch: Orchestrator) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    # TTL desactivado (None) → no-op, no cancela nada aunque sea viejo.
    task.metadata["agentic_state"]["created_at"] = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    assert orch.sweep_expired_suspensions(ttl_seconds=None) == []
    assert orch.sweep_expired_suspensions(ttl_seconds=0) == []
    assert task.status == TaskStatus.AWAITING_APPROVAL


# ===========================================================================
# #4 Traza de progreso por iteración
# ===========================================================================


def test_agentic_progress_event_emitted(orch: Orchestrator) -> None:
    seen: list = []
    orch._bus.subscribe(EventType.AGENTIC_PROGRESS, seen.append)
    hub = _ScriptedHub([
        _resp(tool_calls=[{"id": "c1", "name": "git_log", "arguments": "{}"}]),
        _resp(text="commits reales"),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("analiza el repo")

    assert task.status == TaskStatus.DONE
    assert seen, "se esperaba al menos un evento AGENTIC_PROGRESS"
    evt = seen[0]
    assert evt.payload["task_id"] == task.id
    assert evt.payload["tool"] == "git_log"
    assert evt.payload["iteration"] >= 1
    assert "summary" in evt.payload
