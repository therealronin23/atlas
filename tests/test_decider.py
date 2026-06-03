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


# ---------------------------------------------------------------------------
# Slice 2 — el seam enruta los call-sites del orquestador.
# ---------------------------------------------------------------------------

from collections.abc import Mapping
from pathlib import Path

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus


class FakeDecider:
    """Decisor inyectable que registra cada consulta y devuelve un veredicto fijo."""

    def __init__(self, verdict) -> None:
        self._verdict = verdict
        self.calls: list[tuple[DecisionAction, str, Mapping[str, object]]] = []

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ):
        self.calls.append((action, sanctioned_intent, context))
        return self._verdict


@pytest.fixture
def orch(tmp_path: Path):
    from atlas.core.orchestrator import Orchestrator
    import atlas.governance.governance_l0 as g

    g.GovernanceL0._instance = None
    ws = tmp_path / "atlas"
    ws.mkdir()
    o = Orchestrator(workspace=ws)
    yield o
    g.GovernanceL0._instance = None


# Intent que el clasificador determinista enruta a REQUIRES_APPROVAL.
_APPROVAL_INTENT = "git push al repositorio"


class TestDeciderRoutesCallSites:
    def test_default_human_decider_preserves_suspension(self, orch) -> None:
        # Paridad: sin inyectar nada, el HumanDecider deja la tarea esperando.
        assert isinstance(orch._decider, HumanDecider)
        task = orch.handle_intent(_APPROVAL_INTENT)
        assert task.status == TaskStatus.AWAITING_APPROVAL

    def test_allow_decider_executes_instead_of_suspending(self, orch) -> None:
        fake = FakeDecider(Allow(reason="autónomo"))
        orch.set_decider(fake)
        task = orch.handle_intent(_APPROVAL_INTENT)
        # El seam fue consultado para una decisión de ruta...
        assert any(a.kind == "route" and a.requires_approval for a, _, _ in fake.calls)
        # ...y al autorizar, NO suspendió esperando humano.
        assert task.status != TaskStatus.AWAITING_APPROVAL

    def test_deny_decider_blocks(self, orch) -> None:
        fake = FakeDecider(Deny(reason="incoherente con la intención"))
        orch.set_decider(fake)
        task = orch.handle_intent(_APPROVAL_INTENT)
        assert task.status == TaskStatus.BLOCKED
        assert task.error is not None

    def test_consult_passes_sanctioned_intent_and_context(self, orch) -> None:
        fake = FakeDecider(RequiresHuman(reason="x"))
        orch.set_decider(fake)
        orch.handle_intent(_APPROVAL_INTENT)
        assert fake.calls, "el seam no fue consultado"
        action, sanctioned_intent, context = fake.calls[0]
        assert sanctioned_intent == _APPROVAL_INTENT
        assert "task_id" in context and "source" in context

    def test_set_decider_swaps_implementation(self, orch) -> None:
        fake = FakeDecider(Allow())
        orch.set_decider(fake)
        assert orch._decider is fake
