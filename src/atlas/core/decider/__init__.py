"""Decisor central intercambiable (ADR-040).

Seam único ``decide(action, sanctioned_intent, context) -> Verdict`` por donde se
enrutan todos los puntos de decisión. El humano es una implementación más
(``HumanDecider``), no el camino fijo.
"""

from atlas.core.decider.decider import (
    Allow,
    DecisionAction,
    Decider,
    Deny,
    RequiresHuman,
    Verdict,
    action_hash,
)
from atlas.core.decider.autonomous_decider import AutonomousDecider
from atlas.core.decider.human_decider import HumanDecider
from atlas.core.decider.hybrid_decider import HybridDecider
from atlas.core.decider.revert_registry import (
    MCP_SERVER,
    SNAPSHOT,
    RevertRegistry,
    UndoHandle,
)


def make_decider(name: str | None) -> Decider:
    """Selecciona la implementación del decisor por config (ADR-040 slice 5).

    ``human`` (default) | ``autonomous`` | ``hybrid``. Un valor desconocido cae a
    ``human`` (fail-safe a la conducta actual).
    """
    key = (name or "human").strip().lower()
    if key == "autonomous":
        return AutonomousDecider()
    if key == "hybrid":
        return HybridDecider()
    return HumanDecider()


__all__ = [
    "Allow",
    "AutonomousDecider",
    "DecisionAction",
    "Decider",
    "Deny",
    "HumanDecider",
    "HybridDecider",
    "MCP_SERVER",
    "RequiresHuman",
    "RevertRegistry",
    "SNAPSHOT",
    "UndoHandle",
    "Verdict",
    "action_hash",
    "make_decider",
]
