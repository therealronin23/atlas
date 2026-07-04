"""DecisionRecord — modelo de datos + sinks para el arco copia-digital (slice 1).

El RecordingDecider graba cada llamada a decide() aquí. El split
features-estructuradas / rationale-shredeable es la corrección A del Cónclave:
el merkle hashea features (persistentes), el rationale es texto cifrable y borrable
sin destruir la fila estructural.

Sinks disponibles:
  JsonlDecisionSink  — SOLO test/dev (sin cifrado, no usar con decisiones reales).
  MemoryDecisionSink — producción (SqliteMemoryIndex, Fernet, shred, merkle) en slice 1b.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionRecord:
    """Captura estructurada de una decisión (features + rationale separados).

    Corrección A del Cónclave: las features son inmutables y merkleable; el
    rationale es shredeable sin destruir la fila estructural.
    """

    # Identidad — ata el registro a la acción exacta
    record_id: str           # = action_hash(action, sanctioned_intent)
    action_hash_val: str     # alias explícito para claridad en dumps

    # Features estructuradas (no sensibles, persisten inmutables)
    kind: str
    descriptor: str
    mutating: bool
    reversible: bool
    sensitivity: str
    requires_approval: bool

    # Veredicto
    verdict: str             # "Allow" | "Deny" | "RequiresHuman"

    # Procedencia del decisor
    decider_name: str
    decider_version: str     # hash corto del módulo del decisor

    # Tiempo (bi-temporal: el ts es el valid_from; el corpus evoluciona)
    timestamp_ns: int = field(default_factory=time.monotonic_ns)

    # Rationale — shredeable, potencialmente sensible
    rationale: str | None = None


# ---------------------------------------------------------------------------
# Protocol de sink
# ---------------------------------------------------------------------------

@runtime_checkable
class DecisionSink(Protocol):
    """Receptor de registros de decisión (write-only)."""

    def record(self, rec: DecisionRecord) -> None: ...


# ---------------------------------------------------------------------------
# Sink JSONL (stub dev/test — sin cifrado)
# ---------------------------------------------------------------------------

class JsonlDecisionSink:
    """Escribe decisiones a un archivo JSONL (append-only).

    ADVERTENCIA: sin cifrado. Solo para test/dev. No usar para decisiones
    reales con datos sensibles (sensitivity != "normal").
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, rec: DecisionRecord) -> None:
        row = {
            "record_id": rec.record_id,
            "action_hash": rec.action_hash_val,
            "kind": rec.kind,
            "descriptor": rec.descriptor,
            "mutating": rec.mutating,
            "reversible": rec.reversible,
            "sensitivity": rec.sensitivity,
            "requires_approval": rec.requires_approval,
            "verdict": rec.verdict,
            "decider_name": rec.decider_name,
            "decider_version": rec.decider_version,
            "timestamp_ns": rec.timestamp_ns,
            "rationale": rec.rationale,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Sink en memoria (para tests que no quieren disco)
# ---------------------------------------------------------------------------

class InMemoryDecisionSink:
    """Sink en memoria para tests — no persiste nada."""

    def __init__(self) -> None:
        self.records: list[DecisionRecord] = []

    def record(self, rec: DecisionRecord) -> None:
        self.records.append(rec)
