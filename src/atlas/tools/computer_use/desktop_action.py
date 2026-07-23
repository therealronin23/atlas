"""
Atlas Core — Desktop GUI actions (Gate F/desktop, t3-1-universal-gui-operator).

Hermano de vision_loop.ProposedAction: mismo patrón (frozen dataclass,
kind: Literal[...], requires_approval normalizado siempre en código, nunca
por el LLM que propone la acción — invariante D2), pero con campos propios
de escritorio (coordenadas/texto/combo de tecla) en vez de selector/url de
navegador. No se reutiliza ProposedAction porque sus campos son
específicos de browser y forzarlos a servir dos dominios sería confuso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DesktopActionKind = Literal["stop", "click", "type", "key", "move", "scroll", "drag"]

MUTATING_DESKTOP_ACTIONS: frozenset[DesktopActionKind] = frozenset(
    {"click", "type", "key", "move", "scroll", "drag"}
)


@dataclass(frozen=True)
class DesktopAction:
    kind: DesktopActionKind
    reason: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key_combo: str | None = None
    requires_approval: bool = True


def normalize_desktop_approval(action: DesktopAction) -> DesktopAction:
    """Fuerza requires_approval según MUTATING_DESKTOP_ACTIONS — nunca confía
    en el valor que traiga *action* (invariante D2: la aprobación se decide
    en código, nunca por el LLM/planner que propuso la acción)."""
    return DesktopAction(
        kind=action.kind,
        reason=action.reason,
        x=action.x,
        y=action.y,
        text=action.text,
        key_combo=action.key_combo,
        requires_approval=action.kind in MUTATING_DESKTOP_ACTIONS,
    )
