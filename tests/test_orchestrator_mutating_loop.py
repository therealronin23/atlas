"""
ADR-032 — Tools mutantes dentro del loop agéntico (HITL inline).

El loop agéntico (ADR-031) corre herramientas de LECTURA inline. Cuando el
modelo pide una herramienta MUTANTE de host (browser/editor), el loop se
SUSPENDE: serializa su estado (messages, iterations, tools_used, mutaciones
pendientes) en el registro de pending approval, pasa a AWAITING_APPROVAL y
notifica. Al aprobar, el loop se REANUDA exactamente donde quedó, ejecuta la
mutación (clearance ya concedido) y sigue hasta respuesta final o nueva pausa.

Decisiones cubiertas (ver docs/reference/adr/adr_032_mutating_tools_in_loop.md):
  - dec.1/2  clasificación read/mutate (suspende solo ante mutante)
  - dec.3/4  estado serializado en <task_id>.json bajo `agentic_state`
  - dec.5    todas las mutaciones del turno → una sola aprobación
  - dec.6    DENY → denegación sintética + reanuda (presión MemGPT)
  - dec.7    DENY con abort=True → CANCELLED
  - dec.8    mark_confirmed antes de ejecutar la mutante
  - dec.9    `iterations` persiste a través de suspensiones (tope max_iters)
  - dec.10   `task.suspended` en la cadena Merkle
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus
from atlas.core.orchestrator import Orchestrator


class _ScriptedHub:
    """Hub de inferencia falso que devuelve respuestas pre-escritas en orden.
    Si se agota el guion, repite la última (útil para bucles infinitos)."""

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
    """Editor de host falso: registra cada write con su clearance para poder
    verificar (a) que se ejecutó tras la aprobación y (b) que llevaba el
    clearance task:<id> concedido por mark_confirmed."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, str | None]] = []

    def write_file(self, path, content, clearance=None):  # noqa: ANN001, ANN201
        self.writes.append((str(path), content, clearance))
        return SimpleNamespace(
            ok=True, path=str(path), bytes_written=len(content),
        )


def _write_call(path: str = "f.txt", content: str = "hola") -> dict:
    import json

    return {
        "id": "m1",
        "name": "editor_write",
        "arguments": json.dumps({"path": path, "content": content}),
    }


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


# ===========================================================================
# Lectura inline: sin suspensión (compat ADR-031)
# ===========================================================================


def test_read_tool_runs_inline_no_suspension(orch: Orchestrator) -> None:
    hub = _ScriptedHub([
        _resp(tool_calls=[{"id": "c1", "name": "git_log", "arguments": "{}"}]),
        _resp(text="Estos son los commits reales."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("analiza el repositorio")

    assert task.status == TaskStatus.DONE
    assert "agentic_state" not in task.metadata
    assert task.result["iterations"] == 1
    assert "git_log" in task.result["tools_used"]
    # Nunca pasó por aprobación: 2 llamadas, sin pending
    assert len(hub.calls) == 2
    assert orch.pending_approvals() == []


# ===========================================================================
# Mutante → suspensión
# ===========================================================================


def test_mutating_tool_suspends_loop_to_awaiting_approval(
    orch: Orchestrator,
) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe un archivo nuevo")

    # El loop se suspendió: AWAITING_APPROVAL, estado serializado, mutante NO
    # ejecutada, solo 1 inferencia (la inicial; no se re-infirió).
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL
    assert editor.writes == []
    assert len(hub.calls) == 1

    state = task.metadata["agentic_state"]
    assert state["iterations"] == 1
    assert state["pending_mutations"][0]["name"] == "editor_write"
    assert any(m["role"] == "user" for m in state["messages"])
    assert "created_at" in state

    # Persistido a disco y visible en pending_approvals
    assert (orch._pending_approval_dir / f"{task.id}.json").exists()
    assert any(p["task_id"] == task.id for p in orch.pending_approvals())

    # Auditoría: task.suspended en la cadena
    recent = orch._merkle.tail(40)
    assert any(
        r.action == "task.suspended" and r.task_id == task.id for r in recent
    )


# ===========================================================================
# Aprobar → reanuda y ejecuta la mutación
# ===========================================================================


def test_approve_resumes_loop_and_executes_mutation(
    orch: Orchestrator,
) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([
        _resp(tool_calls=[_write_call(path="nota.txt", content="contenido")]),
        _resp(text="He escrito el archivo."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("crea nota.txt")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    res = orch.approve_pending(task.id, True)

    assert res["status"] == "done"
    assert res["approved"] is True
    assert task.status == TaskStatus.DONE
    # La mutación corrió con el clearance concedido (dec.8)
    assert len(editor.writes) == 1
    path, content, clearance = editor.writes[0]
    assert content == "contenido"
    assert clearance == f"task:{task.id}"
    # Respuesta final del loop reanudado
    assert task.result["resumed"] is True
    assert "escrito" in task.result["text"].lower()
    # Estado limpiado; pending borrado
    assert "agentic_state" not in task.metadata
    assert not (orch._pending_approval_dir / f"{task.id}.json").exists()
    # Se reinyectó el resultado de la mutación al modelo
    assert any(m["role"] == "tool" for m in hub.calls[1].messages)


# ===========================================================================
# Denegar (sin abort) → presión MemGPT, el modelo re-planifica
# ===========================================================================


def test_deny_injects_pressure_and_model_replans(orch: Orchestrator) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([
        _resp(tool_calls=[_write_call()]),
        _resp(text="Entendido, no escribo nada y te propongo otra cosa."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    res = orch.approve_pending(task.id, False)  # deny, abort por defecto False

    # No se ejecutó la mutación, pero el loop SIGUIÓ (re-planificó)
    assert editor.writes == []
    assert res.get("denied_and_resumed") is True
    assert task.status == TaskStatus.DONE
    assert "propongo otra cosa" in task.result["text"]
    # El modelo recibió el resultado sintético de denegación
    tool_msgs = [m for m in hub.calls[1].messages if m["role"] == "tool"]
    assert any("denied" in m["content"] for m in tool_msgs)


# ===========================================================================
# Denegar con abort → CANCELLED
# ===========================================================================


def test_deny_abort_cancels_task(orch: Orchestrator) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    res = orch.approve_pending(task.id, False, abort=True)

    assert task.status == TaskStatus.CANCELLED
    assert res["approved"] is False
    assert editor.writes == []
    # Solo la inferencia inicial; no hubo reanudación
    assert len(hub.calls) == 1
    assert not (orch._pending_approval_dir / f"{task.id}.json").exists()


# ===========================================================================
# Presupuesto de iteraciones persiste a través de suspensiones
# ===========================================================================


def test_iteration_budget_persists_across_suspension(
    orch: Orchestrator,
) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    # Hub que SIEMPRE pide una mutación: cada aprobación reanuda y re-suspende
    # hasta agotar el presupuesto max_iters=5.
    hub = _ScriptedHub([_resp(tool_calls=[_write_call()])])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("edita en bucle infinito")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    approvals = 0
    while task.status == TaskStatus.AWAITING_APPROVAL and approvals < 12:
        orch.approve_pending(task.id, True)
        approvals += 1

    # El tope se respetó a través de las suspensiones: no se reinició el contador
    assert task.status == TaskStatus.DONE
    assert task.result["iterations"] == 5
    # No se ejecutaron más mutaciones que el tope
    assert len(editor.writes) == 5


# ===========================================================================
# Round-trip: el estado sobrevive un reinicio del servicio (sin proceso vivo)
# ===========================================================================


def test_agentic_state_roundtrip_survives_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    ws = tmp_path / "atlas"

    # Proceso 1: suspende el loop y muere.
    o1 = Orchestrator(workspace=ws)
    o1.attach_gate_f_tools(editor=_FakeEditor())
    o1.enable_gate_d_pipeline(
        inference_hub=_ScriptedHub([_resp(tool_calls=[_write_call()])])
    )
    task = o1.handle_intent("escribe un archivo")
    assert task.status == TaskStatus.AWAITING_APPROVAL
    task_id = task.id
    del o1  # simular fin de proceso

    # Proceso 2: arranca limpio, rehidrata desde disco y aprueba.
    editor2 = _FakeEditor()
    hub2 = _ScriptedHub([_resp(text="Archivo escrito tras reinicio.")])
    o2 = Orchestrator(workspace=ws)
    o2.attach_gate_f_tools(editor=editor2)
    o2.enable_gate_d_pipeline(inference_hub=hub2)

    loaded = o2._load_pending_approval(task_id)
    assert loaded is not None
    state = loaded.metadata["agentic_state"]
    assert state["pending_mutations"][0]["name"] == "editor_write"
    assert any(m["role"] == "user" for m in state["messages"])

    res = o2.approve_pending(task_id, True)
    assert res["status"] == "done"
    assert len(editor2.writes) == 1  # la mutación corrió tras el reinicio


# ===========================================================================
# Auditoría: la cadena Merkle registra pausa → aprobación → ejecución
# ===========================================================================


def test_merkle_chain_records_suspend_approve_execute(
    orch: Orchestrator,
) -> None:
    editor = _FakeEditor()
    orch.attach_gate_f_tools(editor=editor)
    hub = _ScriptedHub([
        _resp(tool_calls=[_write_call()]),
        _resp(text="Listo."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("escribe algo auditado")
    orch.approve_pending(task.id, True)

    recent = orch._merkle.tail(60)
    actions = {r.action for r in recent if r.task_id == task.id}
    assert "task.suspended" in actions
    assert "task.approval" in actions
    # La mutación quedó como tool.invoked (agente orchestrator.agentic.editor_write)
    mutation_invoked = [
        r for r in recent
        if r.action == "tool.invoked"
        and r.payload.get("tool") == "editor_write"
    ]
    assert mutation_invoked

    # La cadena entera sigue íntegra tras pausa→aprobación→ejecución
    ok, msg = orch._merkle.verify_chain()
    assert ok, msg
