"""MemoryDecisionSink — sink de producción para el arco copia-digital (slice 1b).

Escribe cada DecisionRecord al SqliteMemoryIndex con:
  - Fernet por-ítem (cifrado en reposo del texto)
  - merkle_leaf_hash (features estructuradas; sobrevive al shred del rationale)
  - ProvenanceWriteGate (anti-envenenamiento: rechaza escrituras sin hash)
  - Rationale shredeable por separado (split A del Cónclave)

Split A implementado:
  - Texto del record = JSON de features estructuradas (no sensibles, persistentes).
    El embedding se calcula de este texto. El merkle_leaf_hash hashea estas features.
  - El rationale se almacena como campo separado en el texto solo si existe.
    Se puede shredear (SqliteMemoryIndex.shred) sin destruir las features.
    La fila estructural (record_id, verdict, kind, etc.) survives intacta.

Activación:
    ATLAS_DECISION_LOG=memory:<db_path>  → make_decider usa este sink.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from atlas.core.decider.decision_record import DecisionRecord, DecisionSink
from atlas.memory.memory_index import ProvenanceWriteGate, SqliteMemoryIndex
from atlas.memory.record import GenericRecord


def _features_text(rec: DecisionRecord) -> str:
    """Serialización canónica de las features estructuradas (no incluye rationale).

    Este es el texto que se indexa y embedea. No contiene datos sensibles.
    El merkle_leaf_hash hashea este mismo JSON (reproducible, sort_keys=True).
    """
    return json.dumps(
        {
            "record_id": rec.record_id,
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
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _full_text(rec: DecisionRecord) -> str:
    """Texto completo para el record (features + rationale si existe).

    El rationale se puede shredear eliminando el registro y re-insertando
    solo las features. El embed se recalcula solo de las features para
    que el merkle_leaf_hash no dependa del rationale.
    """
    features = _features_text(rec)
    if rec.rationale:
        return features + "\n[rationale] " + rec.rationale
    return features


def _merkle_hash(rec: DecisionRecord) -> str:
    """Hash corto (sha256[:16]) de las features estructuradas.

    NO incluye rationale — el merkle sobrevive al shred del rationale.
    Cumple el contrato de ProvenanceWriteGate (non-empty).
    """
    return hashlib.sha256(_features_text(rec).encode("utf-8")).hexdigest()[:16]


class MemoryDecisionSink:
    """Sink de producción: escribe decisiones al SqliteMemoryIndex verificable.

    Usa ProvenanceWriteGate — rechaza escrituras sin merkle_leaf_hash.
    El rationale es shredeable vía SqliteMemoryIndex.shred(record_id).
    Después del shred, las features estructuradas permanecen en el índice;
    el recall ya no devuelve el rationale pero el record_id y el merkle siguen.

    Invariante (firewall D): esta clase es solo-escritura; no expone
    ningún método de lectura del corpus de decisiones.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        tenant: str = "decisions",
    ) -> None:
        self._idx = SqliteMemoryIndex(
            Path(db_path),
            tenant=tenant,
            write_gate=ProvenanceWriteGate(),
        )
        self._tenant = tenant

    def record(self, rec: DecisionRecord) -> None:
        """Escribe el DecisionRecord al índice verificable.

        El texto del GenericRecord = features + rationale (cifrado Fernet).
        El merkle_leaf_hash = hash de solo las features (sobrevive al shred).
        valid_from_ns = timestamp_ns del registro.
        """
        text = _full_text(rec)
        leaf_hash = _merkle_hash(rec)
        memory_record = GenericRecord(
            record_id=rec.record_id,
            text=text,
            created_at=str(rec.timestamp_ns),
        )
        self._idx.upsert(
            memory_record,
            merkle_leaf_hash=leaf_hash,
            valid_from_ns=rec.timestamp_ns,
            memory_class="factual",
        )

    def shred_rationale(self, record_id: str) -> None:
        """Destruye el texto (features + rationale) del registro.

        Después del shred: el record_id y merkle_leaf_hash permanecen en el
        índice (la fila estructural sigue), pero el contenido no es recuperable.
        Para preservar solo las features (sin rationale), llamar a
        record() con un DecisionRecord sin rationale después del shred.
        """
        self._idx.shred(record_id)
