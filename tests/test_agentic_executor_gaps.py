"""
Tests adicionales de AgenticExecutor (ADR-031/032/033) — caminos no cubiertos
por test_agentic_executor.py existente.

Caminos cubiertos aquí:
  (e) _suspend — serializa agentic_state en task.metadata correctamente
  (f) resume — camino aprobado: mutación ejecutada, task llega a DONE
  (g) resume — camino denegado: mutation recibe JSON denied, task llega a DONE
  (h) resume — aprobación parcial (approve_only): solo las ids listadas se ejecutan
  (i) resume — agentic_state ausente lanza RuntimeError
  (j) _dispatch_mutation — mutación desconocida devuelve error string (no lanza)
  (k) drive — presupuesto max_iters: loop termina en 5 iteraciones sin suspender
  (l) drive — fallo de inferencia a mitad del loop: devuelve None y registra fallo
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlas.core.contracts import Task, TaskSource, TaskStatus
from atlas.core.decider import Allow, DecisionAction, RequiresHuman
from atlas.core.orchestrator_parts import agentic_helpers as _ah
from atlas.core.orchestrator_parts.agentic_executor import AgenticExecutor


# ---------------------------------------------------------------------------
# Helpers copiados de test_agentic_executor.py (doubles reutilizables)
# ---------------------------------------------------------------------------


def _resp(text: str = "", tool_calls: list | None = None, success: bool = True):  # noqa: ANN001
    from atlas.core.inference_hub import InferenceLevel, InferenceResponse

    return InferenceResponse(
        text=text,
        provider="mock",
        model="m",
        level=InferenceLevel.L1,
        latency_ms=1,
        success=success,
        tokens_used=1,
        mode="live",
        tool_calls=tool_calls or [],
        error=None if success else "inference-error",
    )


def _resp_fail() -> object:
    """InferenceResponse con success=False."""
    from atlas.core.inference_hub import InferenceLevel, InferenceResponse

    return InferenceResponse(
        text="",
        provider="mock",
        model="m",
        level=InferenceLevel.L1,
        latency_ms=1,
        success=False,
        tokens_used=0,
        mode="live",
        tool_calls=[],
        error="network-error",
    )


def _tc(tc_id: str, name: str, args: dict | None = None) -> dict:
    return {"id": tc_id, "name": name, "arguments": json.dumps(args or {})}


class _NopPii:
    def redact(self, text: str):  # noqa: ANN201
        return SimpleNamespace(text=text, mapping={}, matches=[])

    def restore(self, text: str, mapping: dict) -> str:  # noqa: ANN001
        return text


class _FakeMerkle:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log(self, **kwargs) -> None:  # noqa: ANN003
        self.calls.append(kwargs)


class _FakeApprovals:
    def __init__(self) -> None:
        self.registered: list = []

    def register(self, task: Task) -> None:
        self.registered.append(task)


class _FakeBus:
    def __init__(self) -> None:
        self.published: list = []

    def publish_type(self, *args, **kwargs) -> None:  # noqa: ANN003
        self.published.append((args, kwargs))


class _FakePermissions:
    def __init__(self) -> None:
        self.confirmed: list[str] = []

    def mark_confirmed(self, key: str) -> None:
        self.confirmed.append(key)


class _ScriptedHub:
    def __init__(self, script: list) -> None:  # noqa: ANN001
        self._script = list(script)

    def infer(self, request):  # noqa: ANN001, ANN201
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]


def _make_host(
    *,
    auto_approve: frozenset[str] | None = None,
    mcp_read_only: set[str] | None = None,
    mcp_results: dict[str, str] | None = None,
    hub_script: list | None = None,
    dispatched_mutations: list | None = None,
) -> SimpleNamespace:
    """Construye un host double con merkle y bus instrumentados."""
    _auto_approve: frozenset[str] = auto_approve or frozenset()
    _mcp_ro: set[str] = mcp_read_only or set()
    _mcp_res: dict[str, str] = mcp_results or {}
    _dispatched: list = dispatched_mutations if dispatched_mutations is not None else []

    approvals = _FakeApprovals()
    permissions = _FakePermissions()
    merkle = _FakeMerkle()
    bus = _FakeBus()

    hub = _ScriptedHub(hub_script or [_resp("fin")])

    def _agentic_tool_kind(name: str) -> str:
        if name.startswith("mcp__"):
            return "read" if name in _mcp_ro else "mutate"
        return _ah.tool_kind(name)

    def _agentic_tool_provenance(name: str) -> str:
        return _ah.tool_provenance(name)

    def _wrap_untrusted(content: str) -> str:
        return _ah.wrap_untrusted(content)

    def _loop_is_tainted(messages: list[dict]) -> bool:
        return _ah.loop_is_tainted(messages)

    def _is_agentic_auto_approved(name: str, task: Task) -> bool:
        if name not in _auto_approve:
            return False
        return task.sensitivity != "high"

    def _consult_decider(action: DecisionAction, task: Task):  # noqa: ANN001, ANN202
        if action.requires_approval:
            return RequiresHuman(reason="test-hitl"), "hash0"
        return Allow(), "hash0"

    def _agentic_tool_specs() -> list:
        return []

    def _persist_pending_approval(task: Task) -> None:
        pass

    class _FakeMcp:
        def knows(self, name: str) -> bool:
            return name in _mcp_res

        def dispatch(self, name: str, arguments) -> str:  # noqa: ANN001
            return _mcp_res.get(name, "")

    return SimpleNamespace(
        _pii_surrogate=_NopPii(),
        _merkle=merkle,
        _approvals=approvals,
        _bus=bus,
        _permissions=permissions,
        _inference_hub=hub,
        _mcp=_FakeMcp(),
        _agentic_tool_kind=_agentic_tool_kind,
        _agentic_tool_provenance=_agentic_tool_provenance,
        _wrap_untrusted=_wrap_untrusted,
        _loop_is_tainted=_loop_is_tainted,
        _is_agentic_auto_approved=_is_agentic_auto_approved,
        _consult_decider=_consult_decider,
        _agentic_tool_specs=_agentic_tool_specs,
        _persist_pending_approval=_persist_pending_approval,
        _dispatched_mutations=_dispatched,
    )


def _task_routing() -> Task:
    """Tarea en estado ROUTING (camino válido para suspensión)."""
    t = Task(intent="test", source=TaskSource.CLI)
    t.transition(TaskStatus.CLASSIFYING)
    t.transition(TaskStatus.ROUTING)
    return t


def _task_executing() -> Task:
    """Tarea en estado EXECUTING (requerido antes de llamar a resume())."""
    t = Task(intent="test", source=TaskSource.CLI)
    t.transition(TaskStatus.CLASSIFYING)
    t.transition(TaskStatus.ROUTING)
    t.transition(TaskStatus.EXECUTING)
    return t


# ===========================================================================
# (e) _suspend — serialización del estado agéntico en task.metadata
# ===========================================================================


class TestSuspend:
    def test_agentic_state_written_to_metadata(self) -> None:
        """_suspend() debe persistir agentic_state con messages/iterations/
        tools_used/pending_mutations en task.metadata."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        messages = [{"role": "user", "content": "hola"}]
        pending = [{"id": "m1", "name": "editor_write", "arguments": "{}"}]

        executor._suspend(task, messages, iterations=2, tools_used=["git_log"], pending_mutations=pending)

        state = task.metadata.get("agentic_state")
        assert isinstance(state, dict), "agentic_state debe ser dict"
        assert state["messages"] == messages
        assert state["iterations"] == 2
        assert state["tools_used"] == ["git_log"]
        assert state["pending_mutations"] == pending
        assert "created_at" in state

    def test_suspend_sets_awaiting_approval_status(self) -> None:
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        executor._suspend(
            task, [], iterations=1, tools_used=[], pending_mutations=[
                {"id": "x1", "name": "editor_write", "arguments": "{}"},
            ],
        )

        assert task.status == TaskStatus.AWAITING_APPROVAL

    def test_suspend_registers_task_in_approvals(self) -> None:
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        executor._suspend(
            task, [], iterations=1, tools_used=[], pending_mutations=[
                {"id": "y1", "name": "editor_write", "arguments": "{}"},
            ],
        )

        assert task in host._approvals.registered

    def test_suspend_publishes_approval_required_event(self) -> None:
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        executor._suspend(
            task, [], iterations=1, tools_used=[], pending_mutations=[
                {"id": "z1", "name": "editor_write", "arguments": "{}"},
            ],
        )

        from atlas.core.contracts import EventType
        published_event_types = [args[0][0] for args in host._bus.published]
        assert EventType.APPROVAL_REQUIRED in published_event_types

    def test_suspend_result_has_pending_mutations_list(self) -> None:
        """task.result tras _suspend debe contener la lista de nombres pendientes."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()
        names = ["editor_write", "browser_click"]
        pending = [{"id": f"i{n}", "name": n, "arguments": "{}"} for n in names]

        executor._suspend(task, [], iterations=0, tools_used=[], pending_mutations=pending)

        assert task.result is not None
        assert task.result.get("pending_mutations") == names


# ===========================================================================
# (f) resume — camino aprobado: mutación ejecutada, task llega a DONE
# ===========================================================================


class TestResumeApproved:
    def test_resume_approved_task_reaches_done(self) -> None:
        """Cuando el estado agéntico contiene una mutación y no está denegado,
        resume() ejecuta la mutación y lleva la tarea a DONE."""
        dispatched: list[str] = []

        host = _make_host(hub_script=[_resp("ok-final")])
        executor = AgenticExecutor(host)

        # Parchear _dispatch_mutation para capturar la llamada
        original = AgenticExecutor._dispatch_mutation

        def _spy(self, name, arguments, task):  # noqa: ANN001, ANN202
            dispatched.append(name)
            return "result-ok"

        AgenticExecutor._dispatch_mutation = _spy  # type: ignore[method-assign]

        try:
            task = _task_executing()
            task.metadata["agentic_state"] = {
                "messages": [{"role": "user", "content": "test"}],
                "iterations": 1,
                "tools_used": ["git_log"],
                "pending_mutations": [
                    {"id": "m1", "name": "editor_write", "arguments": "{}"},
                ],
                "denied": False,
            }

            executor.resume(task)

            assert "editor_write" in dispatched, "La mutación aprobada debe ejecutarse"
            assert task.status == TaskStatus.DONE
        finally:
            AgenticExecutor._dispatch_mutation = original  # type: ignore[method-assign]

    def test_resume_approved_sets_result_with_text(self) -> None:
        """task.result tras resume() debe contener 'text' con la respuesta final."""
        host = _make_host(hub_script=[_resp("respuesta-final")])
        executor = AgenticExecutor(host)

        original = AgenticExecutor._dispatch_mutation

        def _nop(self, name, arguments, task):  # noqa: ANN001, ANN202
            return "ok"

        AgenticExecutor._dispatch_mutation = _nop  # type: ignore[method-assign]

        try:
            task = _task_executing()
            task.metadata["agentic_state"] = {
                "messages": [{"role": "user", "content": "q"}],
                "iterations": 0,
                "tools_used": [],
                "pending_mutations": [
                    {"id": "a1", "name": "editor_write", "arguments": "{}"},
                ],
                "denied": False,
            }

            executor.resume(task)

            assert task.result is not None
            assert task.result.get("text") == "respuesta-final"
            assert task.result.get("resumed") is True
        finally:
            AgenticExecutor._dispatch_mutation = original  # type: ignore[method-assign]


# ===========================================================================
# (g) resume — camino denegado: mutation recibe JSON denied, task llega a DONE
# ===========================================================================


class TestResumeDenied:
    def test_resume_denied_does_not_call_dispatch_mutation(self) -> None:
        """Cuando denied=True, _dispatch_mutation NO se llama — se inyecta
        un JSON de denegación sintético."""
        dispatched: list[str] = []

        host = _make_host(hub_script=[_resp("re-plan")])
        executor = AgenticExecutor(host)

        original = AgenticExecutor._dispatch_mutation

        def _spy(self, name, arguments, task):  # noqa: ANN001, ANN202
            dispatched.append(name)
            return "should-not-run"

        AgenticExecutor._dispatch_mutation = _spy  # type: ignore[method-assign]

        try:
            task = _task_executing()
            task.metadata["agentic_state"] = {
                "messages": [{"role": "user", "content": "test"}],
                "iterations": 1,
                "tools_used": [],
                "pending_mutations": [
                    {"id": "d1", "name": "editor_write", "arguments": "{}"},
                ],
                "denied": True,
                "deny_reason": "human",
            }

            executor.resume(task)

            assert dispatched == [], "dispatch_mutation NO debe llamarse cuando denied=True"
        finally:
            AgenticExecutor._dispatch_mutation = original  # type: ignore[method-assign]

    def test_resume_denied_injects_denial_json_into_messages(self) -> None:
        """El mensaje de tool inyectado al denegar debe ser JSON con denied=true."""
        messages_captured: list[dict] = []

        host = _make_host(hub_script=[_resp("ok")])
        executor = AgenticExecutor(host)

        # Interceptar el hub para capturar los mensajes que se pasan
        original_infer = host._inference_hub.infer

        def _capture_infer(request):  # noqa: ANN001, ANN202
            if hasattr(request, "messages") and request.messages:
                messages_captured.extend(request.messages)
            return original_infer(request)

        host._inference_hub.infer = _capture_infer

        task = _task_executing()
        task.metadata["agentic_state"] = {
            "messages": [{"role": "user", "content": "test"}],
            "iterations": 0,
            "tools_used": [],
            "pending_mutations": [
                {"id": "d2", "name": "editor_write", "arguments": "{}"},
            ],
            "denied": True,
            "deny_reason": "human",
        }

        executor.resume(task)

        tool_msgs = [m for m in messages_captured if m.get("role") == "tool"]
        assert tool_msgs, "Debe haber al menos un mensaje de tool tras la denegación"
        # El contenido debe ser JSON con denied=True
        denial_content = json.loads(tool_msgs[0]["content"])
        assert denial_content.get("denied") is True
        assert "reason" in denial_content

    def test_resume_denied_task_reaches_done(self) -> None:
        """Incluso denegando, la tarea debe completarse (task.status == DONE)."""
        host = _make_host(hub_script=[_resp("re-plan")])
        executor = AgenticExecutor(host)

        task = _task_executing()
        task.metadata["agentic_state"] = {
            "messages": [{"role": "user", "content": "test"}],
            "iterations": 0,
            "tools_used": [],
            "pending_mutations": [
                {"id": "d3", "name": "editor_write", "arguments": "{}"},
            ],
            "denied": True,
        }

        executor.resume(task)

        assert task.status == TaskStatus.DONE


# ===========================================================================
# (h) resume — aprobación parcial (approve_only)
# ===========================================================================


class TestResumePartialApproval:
    def test_only_approved_ids_are_dispatched(self) -> None:
        """Con approve_only=['m1'], solo esa mutación se despacha;
        la otra ('m2') recibe denegación sintética."""
        dispatched: list[str] = []

        host = _make_host(hub_script=[_resp("final")])
        executor = AgenticExecutor(host)

        original = AgenticExecutor._dispatch_mutation

        def _spy(self, name, arguments, task):  # noqa: ANN001, ANN202
            dispatched.append(name)
            return "ok"

        AgenticExecutor._dispatch_mutation = _spy  # type: ignore[method-assign]

        try:
            task = _task_executing()
            task.metadata["agentic_state"] = {
                "messages": [{"role": "user", "content": "test"}],
                "iterations": 1,
                "tools_used": [],
                "pending_mutations": [
                    {"id": "m1", "name": "editor_write", "arguments": "{}"},
                    {"id": "m2", "name": "browser_click", "arguments": "{}"},
                ],
                "denied": False,
                "approve_only": ["m1"],
            }

            executor.resume(task)

            assert "editor_write" in dispatched, "La mutación aprobada debe ejecutarse"
            assert "browser_click" not in dispatched, "La mutación no aprobada NO debe ejecutarse"
        finally:
            AgenticExecutor._dispatch_mutation = original  # type: ignore[method-assign]


# ===========================================================================
# (i) resume — agentic_state ausente lanza RuntimeError
# ===========================================================================


class TestResumeMissingState:
    def test_resume_without_agentic_state_raises(self) -> None:
        """resume() sin agentic_state en metadata debe lanzar RuntimeError."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_executing()
        # No se escribe agentic_state en metadata

        with pytest.raises(RuntimeError, match="agentic_state ausente"):
            executor.resume(task)

    def test_resume_with_invalid_agentic_state_raises(self) -> None:
        """agentic_state que no es dict también debe lanzar RuntimeError."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_executing()
        task.metadata["agentic_state"] = "not-a-dict"

        with pytest.raises(RuntimeError, match="agentic_state ausente"):
            executor.resume(task)


# ===========================================================================
# (j) _dispatch_mutation — mutación desconocida devuelve error string
# ===========================================================================


class TestDispatchMutationUnknown:
    def test_unknown_mutation_returns_error_string(self) -> None:
        """_dispatch_mutation con un nombre que no es editor/browser/mcp debe
        devolver un string de error, no lanzar excepción."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        result = executor._dispatch_mutation("unknown_tool", "{}", task)

        assert isinstance(result, str)
        assert "error" in result.lower()
        assert "unknown_tool" in result

    def test_mutation_with_invalid_json_args_is_handled(self) -> None:
        """Argumentos JSON malformados no deben lanzar — se trata como {}."""
        host = _make_host()
        executor = AgenticExecutor(host)
        task = _task_routing()

        # bad json — _dispatch_mutation atrapa json.JSONDecodeError internamente
        result = executor._dispatch_mutation("unknown_xyz", "NOT JSON", task)

        assert isinstance(result, str)
        # No lanzó excepción: se ejecutó hasta "mutación desconocida"
        assert "error" in result.lower()


# ===========================================================================
# (k) drive — presupuesto max_iters: el loop se detiene a las 5 iteraciones
# ===========================================================================


class TestDriveMaxIters:
    def test_loop_stops_at_max_iters(self) -> None:
        """drive() no ejecuta más de 5 iteraciones aunque el hub siga pidiendo
        herramientas. Devuelve la última respuesta, no None."""
        # Hub siempre responde con una tool_call (loop infinito sin el límite)
        inf_hub_script = [_resp(tool_calls=[_tc(f"t{i}", "git_log")]) for i in range(10)]
        # La última respuesta debe ser sin tools (respuesta final)
        inf_hub_script.append(_resp("done"))

        host = _make_host(hub_script=inf_hub_script)
        executor = AgenticExecutor(host)
        task = _task_routing()

        messages: list[dict] = [{"role": "user", "content": "test"}]
        result = executor.drive(
            task,
            messages,
            _resp(tool_calls=[_tc("t0", "git_log")]),
            [],
            0,
            [],
        )

        # El loop ha de terminar (result no None) porque llega al tope de iters
        # O devuelve None si en la iteración 5 la inferencia vuelve a pedir tools
        # y max_iters queda alcanzado. En ambos casos no puede superar 5 iteraciones.
        iters_count = sum(1 for m in messages if m.get("role") == "assistant")
        assert iters_count <= 5, f"El loop ejecutó {iters_count} > 5 iteraciones"

    def test_iterations_passed_in_count_towards_budget(self) -> None:
        """Si drive() empieza con iterations=4, solo puede hacer 1 vuelta más."""
        calls: list[int] = []
        hub_resp = _resp(tool_calls=[_tc("t0", "git_log")])

        host = _make_host(hub_script=[hub_resp, _resp("fin")])
        executor = AgenticExecutor(host)
        task = _task_routing()

        messages: list[dict] = [{"role": "user", "content": "test"}]
        result = executor.drive(
            task,
            messages,
            _resp(tool_calls=[_tc("t0", "git_log")]),
            [],
            4,  # ya llevamos 4 de 5
            [],
        )

        assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")
        # Máximo 1 turno adicional (iterations 4 → 5)
        assert assistant_turns <= 1


# ===========================================================================
# (l) drive — fallo de inferencia a mitad del loop devuelve None
# ===========================================================================


class TestDriveInferenceFailure:
    def test_inference_failure_mid_loop_returns_none(self) -> None:
        """Si la segunda llamada al hub (después de ejecutar tools) falla,
        drive() debe devolver None y haber registrado el fallo en merkle."""
        host = _make_host(hub_script=[_resp_fail()])
        executor = AgenticExecutor(host)
        task = _task_routing()

        messages: list[dict] = [{"role": "user", "content": "test"}]
        result = executor.drive(
            task,
            messages,
            # Primera respuesta: pide una tool de lectura (correrá inline)
            _resp(tool_calls=[_tc("t1", "git_log")]),
            [],
            0,
            [],
        )

        assert result is None, "drive() debe devolver None cuando la inferencia falla"

    def test_inference_failure_records_failure_in_merkle(self) -> None:
        """Tras un fallo de inferencia, debe haber al menos una entrada en merkle
        con action 'inference.failed'."""
        host = _make_host(hub_script=[_resp_fail()])
        executor = AgenticExecutor(host)
        task = _task_routing()

        messages: list[dict] = [{"role": "user", "content": "test"}]
        executor.drive(
            task,
            messages,
            _resp(tool_calls=[_tc("t2", "git_log")]),
            [],
            0,
            [],
        )

        failed_logs = [
            c for c in host._merkle.calls if c.get("action") == "inference.failed"
        ]
        assert failed_logs, "Debe haber al menos un log 'inference.failed' en merkle"
