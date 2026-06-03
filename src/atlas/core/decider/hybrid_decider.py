"""``HybridDecider`` — autonomía graduada por tier (ADR-040 slice 5).

Red de seguridad durante el endurecimiento de invariantes (D6): lo reversible /
bajo riesgo lo decide el ``AutonomousDecider``; lo irreversible (``high``) lo
retoma el ``HumanDecider`` (gate previo) hasta que los invariantes estén
calibrados con métricas reales. El pivote completo a autónomo es un flip de
config, no un borrado de código.
"""

from __future__ import annotations

from collections.abc import Mapping

from atlas.core.decider.autonomous_decider import AutonomousDecider
from atlas.core.decider.decider import DecisionAction, Decider, Verdict
from atlas.core.decider.human_decider import HumanDecider


class HybridDecider:
    """Enruta por tier: ``high`` → humano; el resto → autónomo."""

    def __init__(
        self,
        autonomous: Decider | None = None,
        human: Decider | None = None,
    ) -> None:
        self._autonomous = autonomous or AutonomousDecider()
        self._human = human or HumanDecider()

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict:
        if self._is_high_tier(action):
            return self._human.decide(action, sanctioned_intent, context)
        return self._autonomous.decide(action, sanctioned_intent, context)

    @staticmethod
    def _is_high_tier(action: DecisionAction) -> bool:
        """Tier irreversible: ``sensitivity=high`` queda en manos del humano."""
        return action.sensitivity == "high"
