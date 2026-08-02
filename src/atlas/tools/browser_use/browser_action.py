"""
BrowserAction and approval logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BrowserAction:
    kind: Literal["stop", "navigate", "click", "fill", "extract", "screenshot"]
    reason: str
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    name: str | None = None
    requires_approval: bool = False


def normalize_browser_approval(action: BrowserAction) -> BrowserAction:
    """
    Invariante D2: La aprobación la decide el código, no el modelo.
    Todas las acciones que mutan estado o navegan fuera del dominio de confianza
    requieren aprobación por defecto, excepto extracciones read-only si están permitidas.
    (Para mantenerlo seguro por defecto, forzamos requires_approval=True excepto para 'stop' y 'extract').
    """
    if action.kind in ("stop", "extract"):
        return BrowserAction(
            kind=action.kind,
            reason=action.reason,
            url=action.url,
            selector=action.selector,
            value=action.value,
            name=action.name,
            requires_approval=False,
        )
    return BrowserAction(
        kind=action.kind,
        reason=action.reason,
        url=action.url,
        selector=action.selector,
        value=action.value,
        name=action.name,
        requires_approval=True,
    )
