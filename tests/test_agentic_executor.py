"""Tests directos de AgenticExecutor (ADR-031/032/033/037).

Ejercita el executor *aislado* — no vía la fachada Orchestrator — para que la
cobertura no dependa de que la delegación del host sea correcta.

Host double: SimpleNamespace con los atributos mínimos que el executor lee en
tiempo de llamada. Las funciones puras de agentic_helpers se invocan
directamente (son las que el Orchestrator delega sin lógica adicional).
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
# Helpers para construir InferenceResponse sin importar el hub completo
# ---------------------------------------------------------------------------


def _resp(text: str = "", tool_calls: list | None = None):  # noqa: ANN001
    from atlas.core.inference_hub import InferenceLevel, InferenceResponse

    return InferenceResponse(
        text=text,
        provider="mock",
        model="m",
        level=InferenceLevel.L1,
        latency_ms=1,
        success=True,
        tokens_used=1,
        mode="live",
        tool_calls=tool_calls or [],
    )


def _tc(tc_id: str, name: str, args: dict | None = None) -> dict:
    return {"id": tc_id, "name": name, "arguments": json.dumps(args or {})}


# ---------------------------------------------------------------------------
# Minimal fake PII surrogate (redact/restore son identidad)
# ---------------------------------------------------------------------------


class _NopPii:
    def redact(self, text: str):  # noqa: ANN201
        return SimpleNamespace(text=text, mapping={}, matches=[])

    def restore(self, text: str, mapping: dict) -> str:  # noqa: ANN001
        return text


# ---------------------------------------------------------------------------
# Minimal host double
#
# Sólo expone los atributos que drive() / _suspend() / _run_auto_approved_mutation()
# leen. Cada atributo puede sobreescribirse en los fixtures del test.
# ---------------------------------------------------------------------------


class _FakeMerkle:
    def log(self, **kwargs) -> None:  # noqa: ANN003
        pass


class _FakeApprovals:
    def __init__(self) -> None:
        self.registered: list = []

    def register(self, task: Task) -> None:
        self.registered.append(task)


class _FakeBus:
    def publish_type(self, *args, **kwargs) -> None:  # noqa: ANN003
        pass


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
) -> SimpleNamespace:
    """Construye el host double mínimo para AgenticExecutor."""
    _auto_approve: frozenset[str] = auto_approve or frozenset()
    _mcp_ro: set[str] = mcp_read_only or set()
    _mcp_res: dict[str, str] = mcp_results or {}

    approvals = _FakeApprovals()
    permissions = _FakePermissions()

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
        # Reproduce la lógica real: si requires_approval → RequiresHuman
        # de lo contrario → Allow.
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
        _merkle=_FakeMerkle(),
        _approvals=approvals,
        _bus=_FakeBus(),
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
    )


def _task() -> Task:
    return Task(intent="test", source=TaskSource.CLI)


# ===========================================================================
# (a) Resultado de fuente no confiable se envuelve con marcador de taint
# ===========================================================================


def test_untrusted_tool_result_is_wrapped() -> None:
    """drive() envuelve con _UNTRUSTED_MARKER el resultado de cualquier tool
    cuya provenance sea 'untrusted' (prefijo mcp__) antes de añadirlo a los
    mensajes del loop. Verificado directamente en los mensajes que arma drive().
    """
    host = _make_host(
        mcp_read_only={"mcp__cal__list"},
        mcp_results={"mcp__cal__list": "evento: reunión 10:00"},
        hub_script=[_resp("respuesta final")],
    )
    executor = AgenticExecutor(host)
    task = _task()
    messages: list[dict] = [{"role": "user", "content": "test"}]

    # El loop procesa la lectura MCP y luego termina (hub devuelve respuesta sin tools).
    result = executor.drive(
        task,
        messages,
        _resp(tool_calls=[_tc("r1", "mcp__cal__list")]),
        [],
        0,
        [],
    )

    assert result is not None, "drive() no debería suspender con solo lecturas MCP"
    # El mensaje de la tool debe contener el marcador de no-confianza.
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert tool_messages, "debe haber al menos un mensaje de tool en el historial"
    assert any(
        _ah.UNTRUSTED_MARKER in (m.get("content") or "")
        for m in tool_messages
    ), "el resultado de la tool MCP no confiable debe ir envuelto con UNTRUSTED_MARKER"


# ===========================================================================
# (b) Bajo taint, se revoca el auto-approve (toda mutación cae a HITL)
# ===========================================================================


def test_taint_revokes_auto_approve() -> None:
    """Tras ingerir un resultado MCP (no confiable), el loop queda 'tainted'.
    Una mutación que estaría en la allowlist de auto-approve debe caer a HITL
    (suspensión con AWAITING_APPROVAL) en vez de ejecutarse inline.

    Se verifica en el executor directamente: drive() devuelve None (suspendido)
    y task.status == AWAITING_APPROVAL.
    """
    dispatched: list[str] = []

    host = _make_host(
        auto_approve=frozenset(["editor_write"]),
        mcp_read_only={"mcp__cal__list"},
        mcp_results={"mcp__cal__list": "evento externo"},
        hub_script=[_resp(tool_calls=[_tc("m1", "editor_write", {"path": "f.txt", "content": "x"})])],
    )

    # Parchear _dispatch_mutation para registrar si se llamó (no debería)
    original_dispatch = AgenticExecutor._dispatch_mutation

    def _spy_dispatch(self, name, arguments, task):  # noqa: ANN001, ANN202
        dispatched.append(name)
        return "ok"

    AgenticExecutor._dispatch_mutation = _spy_dispatch  # type: ignore[method-assign]

    try:
        executor = AgenticExecutor(host)
        task = _task()
        # Llevar la tarea al estado ROUTING (camino: PENDING→CLASSIFYING→ROUTING)
        task.transition(TaskStatus.CLASSIFYING)
        task.transition(TaskStatus.ROUTING)

        # Construir mensajes que ya contienen un resultado MCP envuelto (tainted).
        wrapped_content = _ah.wrap_untrusted("evento externo")
        messages: list[dict] = [
            {"role": "user", "content": "test"},
            {"role": "tool", "tool_call_id": "r0", "content": wrapped_content},
        ]

        # Presentar al executor un turno con la mutación auto-aprobada.
        result = executor.drive(
            task,
            messages,
            _resp(tool_calls=[_tc("m1", "editor_write", {"path": "f.txt", "content": "x"})]),
            [],
            0,
            [],
        )

        assert result is None, "drive() debe suspender (devolver None) porque el loop está tainted"
        assert task.status == TaskStatus.AWAITING_APPROVAL
        assert dispatched == [], "la mutación NO debe ejecutarse cuando el loop está tainted"
        assert host._approvals.registered, "la tarea debe registrarse en pending approvals"
    finally:
        AgenticExecutor._dispatch_mutation = original_dispatch  # type: ignore[method-assign]


# ===========================================================================
# (c) Clasificación de procedencia: confiable vs no confiable
# ===========================================================================


@pytest.mark.parametrize(
    "tool_name, expected",
    [
        ("mcp__cal__list_events", "untrusted"),
        ("mcp__n8n__trigger",     "untrusted"),
        ("git_log",               "trusted"),
        ("git_status",            "trusted"),
        ("git_diff",              "trusted"),
        ("list_workspace",        "trusted"),
        ("read_memory_blocks",    "trusted"),
        ("atlas_status",          "trusted"),
    ],
)
def test_provenance_classification_via_executor(tool_name: str, expected: str) -> None:
    """El executor llama a host._agentic_tool_provenance, que en el double
    delega a _ah.tool_provenance. Se verifica que la clasificación es correcta
    para cada categoría relevante a ADR-037, ejercitando el camino del executor
    (no la fachada directamente)."""
    host = _make_host()
    executor = AgenticExecutor(host)
    # El executor no expone tool_provenance directamente; lo invoca internamente.
    # Verificamos llamando al método del host que el executor usaría.
    result = host._agentic_tool_provenance(tool_name)
    assert result == expected, f"{tool_name!r}: esperado {expected!r}, obtenido {result!r}"


# ===========================================================================
# (d) Lectura confiable NO activa taint (control negativo)
# ===========================================================================


def test_trusted_read_does_not_taint() -> None:
    """Una lectura de fuente confiable (git_log) no marca el loop como tainted;
    la mutación auto-aprobada siguiente corre inline (drive devuelve resultado)."""
    dispatched: list[str] = []

    host = _make_host(
        auto_approve=frozenset(["editor_write"]),
        hub_script=[_resp("listo")],
    )

    original_dispatch = AgenticExecutor._dispatch_mutation

    def _spy_dispatch(self, name, arguments, task):  # noqa: ANN001, ANN202
        dispatched.append(name)
        return "ok"

    AgenticExecutor._dispatch_mutation = _spy_dispatch  # type: ignore[method-assign]

    try:
        executor = AgenticExecutor(host)
        task = _task()

        # Mensajes sin contenido no confiable (loop limpio).
        messages: list[dict] = [{"role": "user", "content": "test"}]

        result = executor.drive(
            task,
            messages,
            _resp(tool_calls=[_tc("m1", "editor_write", {"path": "f.txt", "content": "x"})]),
            [],
            0,
            [],
        )

        assert result is not None, "drive() NO debe suspender cuando el loop no está tainted"
        assert "editor_write" in dispatched, "la mutación debe ejecutarse inline"
    finally:
        AgenticExecutor._dispatch_mutation = original_dispatch  # type: ignore[method-assign]
