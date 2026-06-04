"""ADR-039 slice 2 — tipos del Analyst (candidato → resumen tipado → propuesta).

Frontera datos/control de CaMeL (ADR-037 capa 5): el ``raw_excerpt`` de cada
``Source`` es **prosa NO confiable** (foro/registry) y solo lo toca el
processing-LLM del Analyst. Todo lo demás de este módulo son **campos tipados y
acotados** — lo único que cruza al control-LLM y al gate de corroboración. Los
límites de longitud no son cosméticos: acotan el espacio para instrucciones
camufladas en un resumen (riesgo honesto del ADR §Riesgos).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROVENANCE_AUTHORITATIVE = "authoritative"
PROVENANCE_COMMUNITY = "community"

# Cotas de longitud para los campos tipados (anti-instrucción-camuflada).
_NAME_MAX = 96
_VERSION_MAX = 32
_MAINTAINER_MAX = 96
_PURPOSE_MAX = 280


def _norm(value: str | None, cap: int) -> str:
    """Normaliza un campo tipado: str, recortado y acotado en longitud."""
    return (value or "").strip()[:cap]


@dataclass(frozen=True)
class Source:
    """Una fuente de un candidato, etiquetada por procedencia.

    ``raw_excerpt`` es contenido NO confiable: nunca llega al control-LLM ni al
    gate; solo lo digiere el processing-LLM tras ``wrap_untrusted``."""

    provenance: str
    url: str
    raw_excerpt: str

    @property
    def is_authoritative(self) -> bool:
        return self.provenance == PROVENANCE_AUTHORITATIVE


@dataclass(frozen=True)
class McpCandidate:
    """Candidato de server MCP descubierto (input del Analyst).

    Lo que un Scout externo emitirá (slice 1-literal / 5). En este slice se
    recibe ya formado para no acoplar el Analyst al descubrimiento."""

    name: str
    version: str
    cmd: list[str]
    declared_tools: list[str]
    sources: list[Source]


@dataclass(frozen=True)
class DepCandidate:
    """Dependencia PyPI con un bump disponible (ADR-039 slice 6).

    ``current`` es el piso declarado en ``pyproject`` (p.ej. ``8.1`` de
    ``click>=8.1``); ``latest`` la última estable publicada en PyPI. ``source``
    es siempre autoritativa (el JSON de PyPI). El bump se materializa como patch
    revisable vía ColdUpdate — nunca se aplica solo."""

    name: str
    current: str
    latest: str
    source: Source


@dataclass(frozen=True)
class TypedSummary:
    """Resumen TIPADO que el processing-LLM extrae de una fuente no confiable.

    Es la única salida del processing-LLM y el único input del control-LLM y del
    gate. Campos acotados: no hay prosa libre que pueda portar instrucciones."""

    name: str
    version: str
    maintainer: str
    purpose: str

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "TypedSummary":
        return cls(
            name=_norm(data.get("name"), _NAME_MAX),
            version=_norm(data.get("version"), _VERSION_MAX),
            maintainer=_norm(data.get("maintainer"), _MAINTAINER_MAX),
            purpose=_norm(data.get("purpose"), _PURPOSE_MAX),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "maintainer": self.maintainer,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class Evidence:
    """Un eslabón de la cadena de evidencia: qué fuente respalda (o no) la
    afirmación clave del candidato."""

    url: str
    provenance: str
    corroborates: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "provenance": self.provenance,
            "corroborates": self.corroborates,
        }


@dataclass(frozen=True)
class McpProposal:
    """Propuesta MCP tipada lista para HITL. Solo se materializa si el gate de
    corroboración pasa (≥1 fuente autoritativa). ``status`` reusa el vocabulario
    de estados del ADR (``proposed`` ← esperando el botón humano)."""

    id: str
    capability: str
    version: str
    cmd: list[str]
    purpose: str
    risks: list[str]
    evidence: list[Evidence]
    status: str = "proposed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "version": self.version,
            "cmd": list(self.cmd),
            "purpose": self.purpose,
            "risks": list(self.risks),
            "evidence": [e.to_dict() for e in self.evidence],
            "status": self.status,
        }
