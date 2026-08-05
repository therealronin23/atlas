"""T4.2 — Criba de candidatos con razones nombradas.

Reescrito 2026-08-06. La versión anterior escribía `status = "dissected"` sin
diseccionar nada ("Simulación de la disección") y decidía con
`stars > 10`. Un umbral de estrellas no es una disección, y llamarlo así hacía
que el resto de la cadena tratara una suposición como un hecho verificado.

Este módulo no pretende ser lo que no es. **No** analiza el código del
candidato: eso es trabajo del pipeline de vetting MCP (ADR-075/076), que ya
existe y corre en sandbox. Lo que hace es la criba BARATA previa, sobre campos
que la propia fuente publica, y deja constancia de POR QUÉ descarta.

Regla: cada rechazo lleva una razón nombrada. Un booleano sin motivo es lo que
convirtió la versión anterior en incomprobable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from atlas.discovery.scout import Candidate

logger = logging.getLogger(__name__)

# Un repo sin empujes en año y medio no es un candidato de absorción: el coste
# de mantener lo absorbido recae en Atlas. Generoso a propósito — descartar de
# más en la criba barata es peor que dejar pasar a la cara, que sí inspecciona.
MAX_STALE_DAYS = 540


@dataclass(frozen=True)
class Dissection:
    """Veredicto de la criba barata. `reasons` vacío ⇔ `eligible` True."""

    candidate: Candidate
    eligible: bool
    reasons: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.candidate.name

    @property
    def source(self) -> str:
        return self.candidate.source


class DissectionPipeline:
    """Criba barata previa al vetting caro. Sin estado entre candidatos: la
    versión anterior acumulaba en `self.dissected_candidates`, lo que hacía que
    el resultado dependiera del orden de las llamadas."""

    def __init__(self, *, max_stale_days: int = MAX_STALE_DAYS, now: datetime | None = None) -> None:
        self._max_stale_days = max_stale_days
        self._now = now or datetime.now(timezone.utc)

    def dissect(self, candidate: Candidate) -> Dissection:
        reasons: list[str] = []
        if candidate.archived:
            reasons.append("archivado")
        if not candidate.license:
            # Sin licencia declarada, absorber es un riesgo legal, no técnico.
            reasons.append("sin_licencia")
        if not candidate.url:
            reasons.append("sin_url")
        if self._is_stale(candidate.pushed_at):
            reasons.append("abandonado")
        return Dissection(candidate, not reasons, tuple(reasons))

    def _is_stale(self, pushed_at: str | None) -> bool:
        if not pushed_at:
            # Fecha ausente = no medible. No medible NO es abandonado: inventar
            # un rechazo por falta de dato es el error que este módulo corrige.
            return False
        try:
            pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if pushed.tzinfo is None:
            pushed = pushed.replace(tzinfo=timezone.utc)
        return pushed < self._now - timedelta(days=self._max_stale_days)
