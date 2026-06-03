"""ADR-040 slice 1 — seam Decider + HumanDecider (paridad con el HITL de hoy).

Verifica que ``HumanDecider`` reproduce la decisión que hoy vive inline en los
cuatro call-sites del orquestador: ``REQUIRES_APPROVAL`` o ``sensitivity=high``
→ suspender (``RequiresHuman``); en otro caso → proceder (``Allow``).
"""

from __future__ import annotations

from atlas.core.decider import (
    Allow,
    DecisionAction,
    Decider,
    Deny,
    HumanDecider,
    RequiresHuman,
)


def _decide(action: DecisionAction):
    return HumanDecider().decide(action, sanctioned_intent="t", context={})


class TestHumanDeciderParity:
    def test_requires_approval_suspends(self) -> None:
        verdict = _decide(DecisionAction(kind="route", requires_approval=True))
        assert isinstance(verdict, RequiresHuman)

    def test_high_sensitivity_always_suspends(self) -> None:
        # Regla constitucional #4: high fuerza aprobación aunque no la pida.
        verdict = _decide(
            DecisionAction(kind="route", requires_approval=False, sensitivity="high")
        )
        assert isinstance(verdict, RequiresHuman)

    def test_high_sensitivity_overrides_even_without_flag(self) -> None:
        verdict = _decide(
            DecisionAction(kind="gate_f", requires_approval=False, sensitivity="high")
        )
        assert isinstance(verdict, RequiresHuman)

    def test_no_approval_normal_sensitivity_allows(self) -> None:
        verdict = _decide(
            DecisionAction(kind="route", requires_approval=False, sensitivity="normal")
        )
        assert isinstance(verdict, Allow)

    def test_mutating_alone_does_not_force_human(self) -> None:
        # En el flujo actual la mutación se traduce a requires_approval en el
        # call-site; el flag mutating por sí solo no suspende (slice 1).
        verdict = _decide(
            DecisionAction(kind="agentic_tool", requires_approval=False, mutating=True)
        )
        assert isinstance(verdict, Allow)

    def test_reason_propagates(self) -> None:
        verdict = _decide(
            DecisionAction(kind="route", requires_approval=True, reason="riesgo X")
        )
        assert isinstance(verdict, RequiresHuman)
        assert verdict.reason == "riesgo X"

    def test_reason_defaults_when_absent(self) -> None:
        verdict = _decide(DecisionAction(kind="route", requires_approval=True))
        assert isinstance(verdict, RequiresHuman)
        assert verdict.reason == "requires_approval"


class TestDeciderContract:
    def test_human_decider_satisfies_protocol(self) -> None:
        assert isinstance(HumanDecider(), Decider)

    def test_verdicts_are_frozen(self) -> None:
        import dataclasses

        import pytest

        verdict = Allow(reason="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            verdict.reason = "y"  # type: ignore[misc]

    def test_action_is_frozen(self) -> None:
        import dataclasses

        import pytest

        action = DecisionAction(kind="route")
        with pytest.raises(dataclasses.FrozenInstanceError):
            action.kind = "other"  # type: ignore[misc]

    def test_verdict_types_are_distinct(self) -> None:
        assert not isinstance(Allow(), Deny)
        assert not isinstance(Deny(), RequiresHuman)
        assert not isinstance(RequiresHuman(), Allow)
