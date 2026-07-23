"""Tests T3 (t3-1-universal-gui-operator) — DesktopPlanner: LLM -> plan de
DesktopAction, JSON tipado fail-closed. Invariante D2: requires_approval
nunca viene del LLM (ni siquiera está en el schema de entrada) — cualquier
JSON inválido, con campo desconocido, o kind fuera del literal produce un
plan de un solo paso [stop], nunca ejecución adivinada."""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.tools.computer_use.desktop_planner import DesktopPlanner


def _make_hub(response_text: str, success: bool = True) -> MagicMock:
    hub = MagicMock()
    resp = MagicMock()
    resp.success = success
    resp.text = response_text
    resp.error = None if success else "error de prueba"
    hub.infer_for_role.return_value = resp
    return hub


def test_valid_plan_is_parsed_into_desktop_actions() -> None:
    hub = _make_hub(
        '{"steps": ['
        '{"kind": "click", "x": 100, "y": 200, "reason": "boton submit"},'
        '{"kind": "type", "text": "hola", "reason": "rellenar campo"}'
        "]}"
    )
    planner = DesktopPlanner(hub)

    plan = planner.plan("rellena el formulario")

    assert [a.kind for a in plan] == ["click", "type"]
    assert plan[0].x == 100 and plan[0].y == 200
    assert plan[1].text == "hola"
    assert all(a.requires_approval is True for a in plan)  # mutantes -> True


def test_stop_action_does_not_require_approval() -> None:
    hub = _make_hub('{"steps": [{"kind": "stop", "reason": "nada que hacer"}]}')
    planner = DesktopPlanner(hub)

    plan = planner.plan("no hagas nada")

    assert len(plan) == 1
    assert plan[0].kind == "stop"
    assert plan[0].reason == "nada que hacer"
    assert plan[0].requires_approval is False


def test_malformed_json_falls_back_to_stop_plan() -> None:
    hub = _make_hub("esto no es JSON en absoluto")
    planner = DesktopPlanner(hub)

    plan = planner.plan("tarea cualquiera")

    assert len(plan) == 1
    assert plan[0].kind == "stop"
    assert plan[0].requires_approval is False


def test_unknown_kind_falls_back_to_stop_plan() -> None:
    hub = _make_hub('{"steps": [{"kind": "delete_everything", "reason": "x"}]}')
    planner = DesktopPlanner(hub)

    plan = planner.plan("tarea cualquiera")

    assert len(plan) == 1
    assert plan[0].kind == "stop"


def test_llm_cannot_set_requires_approval_directly() -> None:
    """El schema de entrada no tiene requires_approval — si el LLM intenta
    colarlo, extra=forbid rechaza el paso completo (fail-closed), no lo
    ignora silenciosamente ni lo respeta."""
    hub = _make_hub(
        '{"steps": [{"kind": "click", "x": 1, "y": 1, "reason": "x", '
        '"requires_approval": false}]}'
    )
    planner = DesktopPlanner(hub)

    plan = planner.plan("intento de bypass")

    assert len(plan) == 1
    assert plan[0].kind == "stop"


def test_code_fence_around_json_is_stripped() -> None:
    hub = _make_hub(
        '```json\n{"steps": [{"kind": "stop", "reason": "listo"}]}\n```'
    )
    planner = DesktopPlanner(hub)

    plan = planner.plan("tarea con fences")

    assert plan[0].kind == "stop"


def test_infer_failure_falls_back_to_stop_plan() -> None:
    hub = _make_hub("", success=False)
    planner = DesktopPlanner(hub)

    plan = planner.plan("tarea cualquiera")

    assert len(plan) == 1
    assert plan[0].kind == "stop"


def test_plan_is_truncated_to_max_steps() -> None:
    steps = ",".join(f'{{"kind": "stop", "reason": "{i}"}}' for i in range(5))
    hub = _make_hub(f'{{"steps": [{steps}]}}')
    planner = DesktopPlanner(hub, max_steps=2)

    plan = planner.plan("plan largo")

    assert len(plan) == 2
