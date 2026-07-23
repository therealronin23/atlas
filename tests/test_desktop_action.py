"""Tests T3 (t3-1-universal-gui-operator) — DesktopAction, espejo de
test_vision_loop.py: la aprobación se decide en código, nunca por el LLM
que propuso la acción (invariante D2)."""

from __future__ import annotations

from atlas.tools.computer_use.desktop_action import (
    MUTATING_DESKTOP_ACTIONS,
    DesktopAction,
    normalize_desktop_approval,
)


def test_stop_action_normalizes_to_no_approval_required() -> None:
    action = DesktopAction(kind="stop", reason="nada que hacer", requires_approval=True)

    normalized = normalize_desktop_approval(action)

    assert normalized.requires_approval is False


def test_mutating_action_is_forced_to_require_approval() -> None:
    action = DesktopAction(
        kind="click", reason="boton detectado", x=100, y=200, requires_approval=False,
    )

    normalized = normalize_desktop_approval(action)

    assert normalized.requires_approval is True
    assert normalized.x == 100
    assert normalized.y == 200


def test_all_mutating_kinds_are_forced_to_require_approval() -> None:
    for kind in MUTATING_DESKTOP_ACTIONS:
        action = DesktopAction(kind=kind, reason="x", requires_approval=False)
        assert normalize_desktop_approval(action).requires_approval is True


def test_stop_is_not_in_mutating_set() -> None:
    assert "stop" not in MUTATING_DESKTOP_ACTIONS
