"""T4.3 — Corroboración cruzada entre fuentes independientes.

Reescrito 2026-08-06. La versión anterior se llamaba
`cross_reference_signals` y hacía esto:

    if cand.get("absorption_ready") and cand.get("stars", 0) > 50:

Eso no cruza señales. `absorption_ready` ya venía de mirar `stars`, así que la
"verificación" consultaba dos veces la MISMA señal con dos umbrales distintos
(10 y 50) y llamaba corroboración al resultado. Un candidato con muchas
estrellas y un solo aval pasaba como "verificado".

Corroborar es que **fuentes independientes coincidan**. Aquí eso significa:
el mismo candidato, elegible, avalado por al menos dos CANALES distintos
(`Candidate.source`). Dos búsquedas diferentes en la API de GitHub son el
mismo canal — por eso `EcosystemScout._source_label` etiqueta el canal y no
la consulta.

Corroborar no promueve nada: es una señal de entrada al vetting real
(ADR-075/076), que sigue siendo quien decide en sandbox y con consentimiento.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from atlas.discovery.pipeline import Dissection

logger = logging.getLogger(__name__)

# Cuántos canales independientes hacen falta. Dos es el mínimo con el que la
# palabra "cruzada" significa algo.
MIN_INDEPENDENT_SOURCES = 2


@dataclass(frozen=True)
class Corroborated:
    """Candidato avalado por más de un canal. `sources` es la evidencia."""

    name: str
    url: str
    sources: tuple[str, ...]
    stars: int


@dataclass
class _Accumulator:
    """Acumulador tipado por candidato. Un `dict[str, object]` obligaba a
    reafirmar tipos en cada acceso; esto lo hace innecesario."""

    url: str
    stars: int
    sources: set[str]


class EcosystemDigestion:
    """Sin estado: la versión anterior acumulaba en `self.catalog`, así que dos
    llamadas seguidas devolvían resultados distintos con la misma entrada."""

    def __init__(self, *, min_sources: int = MIN_INDEPENDENT_SOURCES) -> None:
        self._min_sources = min_sources

    def corroborate(self, dissections: Iterable[Dissection]) -> list[Corroborated]:
        by_name: dict[str, _Accumulator] = {}
        for item in dissections:
            if not item.eligible:
                # Un inelegible repetido en diez canales sigue siendo inelegible:
                # la corroboración confirma existencia, no arregla defectos.
                continue
            entry = by_name.get(item.name)
            if entry is None:
                entry = _Accumulator(item.candidate.url, item.candidate.stars, set())
                by_name[item.name] = entry
            entry.sources.add(item.source)
            entry.stars = max(entry.stars, item.candidate.stars)

        out: list[Corroborated] = []
        for name, acc in sorted(by_name.items()):
            if len(acc.sources) < self._min_sources:
                continue
            logger.info("candidato corroborado por %d canales: %s", len(acc.sources), name)
            out.append(
                Corroborated(
                    name=name,
                    url=acc.url,
                    sources=tuple(sorted(acc.sources)),
                    stars=acc.stars,
                )
            )
        return out
