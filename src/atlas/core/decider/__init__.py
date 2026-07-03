"""Decisor central intercambiable (ADR-040).

Seam único ``decide(action, sanctioned_intent, context) -> Verdict`` por donde se
enrutan todos los puntos de decisión. El humano es una implementación más
(``HumanDecider``), no el camino fijo.

Opt-in de grabación (slice 1 copia-digital):
    ATLAS_DECISION_LOG=<path>  → envuelve el decisor en RecordingDecider con JsonlDecisionSink.
    Sin la variable → cero cambio de comportamiento.
"""

import os

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
    COLD_PATCH,
    MCP_SERVER,
    SNAPSHOT,
    RevertRegistry,
    UndoHandle,
)
from atlas.core.decider.decision_record import (
    DecisionRecord,
    DecisionSink,
    InMemoryDecisionSink,
    JsonlDecisionSink,
)
from atlas.core.decider.recording_decider import RecordingDecider
from atlas.core.decider.memory_decision_sink import MemoryDecisionSink
from atlas.core.decider.twin_decider import TwinDecider, ShadowPredictor, ShadowAccuracyLog, MIN_CORPUS_SIZE


def make_decider(name: str | None) -> Decider:
    """Selecciona la implementación del decisor por config (ADR-040 slice 5).

    ``human`` (default) | ``autonomous`` | ``hybrid``. Un valor desconocido cae a
    ``human`` (fail-safe a la conducta actual).

    Con ``ATLAS_DECISION_LOG=<path>`` envuelve el resultado en RecordingDecider
    (slice 1 copia-digital). Sin la variable, cero cambio de comportamiento.
    """
    key = (name or "human").strip().lower()
    if key == "autonomous":
        base: Decider = AutonomousDecider()
    elif key == "hybrid":
        base = HybridDecider()
    else:
        base = HumanDecider()

    log_path = os.environ.get("ATLAS_DECISION_LOG", "").strip()
    if log_path:
        sink = JsonlDecisionSink(log_path)
        return RecordingDecider(base, sink)

    return base


__all__ = [
    "Allow",
    "AutonomousDecider",
    "DecisionAction",
    "Decider",
    "DecisionRecord",
    "DecisionSink",
    "Deny",
    "HumanDecider",
    "HybridDecider",
    "InMemoryDecisionSink",
    "JsonlDecisionSink",
    "COLD_PATCH",
    "MCP_SERVER",
    "RecordingDecider",
    "RequiresHuman",
    "RevertRegistry",
    "SNAPSHOT",
    "UndoHandle",
    "Verdict",
    "action_hash",
    "make_decider",
    "MIN_CORPUS_SIZE",
    "ShadowAccuracyLog",
    "ShadowPredictor",
    "TwinDecider",
]
