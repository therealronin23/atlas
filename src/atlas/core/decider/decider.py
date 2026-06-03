"""Seam de decisión central (ADR-040 slice 1).

Punto único por donde, más adelante, entrará la autonomía con un flip de config
(`human | autonomous | hybrid`). En slice 1 solo se define el contrato; los
call-sites del orquestador se enrutan aquí en slice 2.

Modelo de rumbo: human-ON-the-loop. El veredicto objetivo es ``Allow | Deny`` sin
``Escalate`` bloqueante. ``RequiresHuman`` es el estado transitorio que reproduce
el HITL de hoy y que las slices futuras irán retirando a medida que el
``AutonomousDecider`` (invariantes deterministas) asuma lo reversible.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DecisionAction:
    """Acción candidata que un generador quiere ejecutar.

    ``kind`` identifica el call-site de origen (``route`` / ``gate_f`` /
    ``agentic_tool``) para telemetría y tiering futuro. ``descriptor`` (tool name
    o fragmento de intent) servirá para el ``action_hash`` de slice 3.
    """

    kind: str
    requires_approval: bool = False
    sensitivity: str = "normal"
    mutating: bool = False
    reason: str = ""
    descriptor: str = ""


@dataclass(frozen=True)
class Allow:
    """Procede sin intervención humana."""

    reason: str = ""


@dataclass(frozen=True)
class Deny:
    """No se ejecuta; el generador re-planifica (presión)."""

    reason: str = ""


@dataclass(frozen=True)
class RequiresHuman:
    """Suspende y espera el veredicto humano (HITL actual).

    Estado transitorio: existe para mantener paridad con el flujo de hoy. La
    dirección del proyecto es retirarlo en favor de ``Allow | Deny`` autónomo.
    """

    reason: str = ""


Verdict = Allow | Deny | RequiresHuman


@runtime_checkable
class Decider(Protocol):
    """Contrato del decisor intercambiable.

    El humano es UNA implementación (``HumanDecider``), no el camino fijo. El
    pivote a autonomía es añadir una implementación + flip de config, no
    refactorizar los call-sites.
    """

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict: ...
