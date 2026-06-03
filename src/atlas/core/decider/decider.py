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

import hashlib
import json
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


def action_hash(action: DecisionAction, sanctioned_intent: str) -> str:
    """Hash determinista que ata un veredicto a la acción exacta decidida.

    ADR-036 P2 / ADR-040 slice 3: el veredicto queda ligado a este hash. Si la
    acción o la intención sancionada cambian, el hash cambia y un OK previo deja
    de aplicar. ``reason`` se excluye: es explicativo, no parte de la identidad.
    """
    canonical = json.dumps(
        {
            "kind": action.kind,
            "descriptor": action.descriptor,
            "mutating": action.mutating,
            "sensitivity": action.sensitivity,
            "requires_approval": action.requires_approval,
            "sanctioned_intent": sanctioned_intent,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
