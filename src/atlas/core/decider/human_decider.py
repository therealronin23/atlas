"""``HumanDecider`` — el HITL de hoy expresado como implementación del seam.

ADR-040 slice 1: reproduce EXACTAMENTE la decisión que hoy vive inline en los
cuatro call-sites del orquestador. No cambia conducta; solo concentra el "¿esto
requiere humano?" en un sitio para que slice 2 enrute los call-sites por aquí.

Regla constitucional #4 (AGENTS.md): ``sensitivity="high"`` SIEMPRE fuerza
aprobación, con independencia del patrón. Es un invariante, no una heurística.
"""

from __future__ import annotations

from collections.abc import Mapping

from atlas.core.decider.decider import (
    Allow,
    DecisionAction,
    RequiresHuman,
    Verdict,
)


class HumanDecider:
    """Devuelve ``RequiresHuman`` cuando hoy se suspendería; si no, ``Allow``."""

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict:
        if action.sensitivity == "high":
            return RequiresHuman(reason=action.reason or "sensitivity=high")
        if action.requires_approval:
            return RequiresHuman(reason=action.reason or "requires_approval")
        return Allow(reason="auto")
