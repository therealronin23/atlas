"""
Atlas Core — MemoryTrunk: la raíz de memoria del MCP trunk portable (F1).

Capa NEUTRA, transport-agnostic: tools `add` / `recall` / `supersede` sobre el
sustrato verificable (`SqliteMemoryIndex`). NO sabe nada de MCP; el shell
FastMCP se monta encima (cuando el SDK esté disponible) llamando a estos métodos.
Esto realiza el cross-play: el "save file" (memoria + procedencia Merkle) vive en
una capa local agnóstica de cliente; cualquier agente que hable MCP la lee/escribe.

Diseño: docs/design/mcp_trunk_portable.md (F1). Honesto: la arquitectura
tronco+raíces es commodity; el moat es ESTE contenido (procedencia + supersesión
+ validez temporal) expuesto portable.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


@dataclass(frozen=True)
class RecallHit:
    """Un resultado de recall con su procedencia. `merkle_leaf_hash` puede ser
    None si el record entró sin enlace Merkle (índice sin logger)."""

    record_id: str
    text: str
    score: float
    matched: bool
    merkle_leaf_hash: str | None


class MemoryTrunk:
    """Tools neutras sobre el sustrato. Reutiliza directo el motor Python."""

    def __init__(self, index: SqliteMemoryIndex) -> None:
        self._index = index

    def add(
        self, text: str, *, record_id: str | None = None, record_type: str | None = None
    ) -> str:
        """Recuerda `text`. Devuelve el id (generado si no se da)."""
        rid = record_id if record_id is not None else uuid.uuid4().hex
        created_at = str(time.time_ns())
        self._index.upsert(GenericRecord(rid, text, created_at, record_type))
        return rid

    def recall(self, query: str, k: int = 5) -> list[RecallHit]:
        """Devuelve hasta `k` candidatos VIGENTES ordenados por relevancia, con
        texto y procedencia. OJO: devuelve candidatos aunque ninguno supere el
        umbral — mira `matched` para distinguir un acierto real del ruido top-k.
        Lista vacía solo si el índice está vacío."""
        results = self._index.recall_all(query, k=k)
        hits: list[RecallHit] = []
        for r in results:
            text = self._index.text_of(r.lesson_id)
            if text is None:
                continue
            hits.append(
                RecallHit(
                    record_id=r.lesson_id,
                    text=text,
                    score=r.score,
                    matched=r.matched,
                    merkle_leaf_hash=self._index.merkle_leaf_hash(r.lesson_id),
                )
            )
        return hits

    def supersede(self, old_id: str, new_text: str, *, record_id: str | None = None) -> str:
        """`new_text` reemplaza a `old_id`: la vieja caduca (auditable, no se
        borra) y la nueva entra vigente con lineage. Devuelve el id nuevo."""
        rid = record_id if record_id is not None else uuid.uuid4().hex
        created_at = str(time.time_ns())
        self._index.supersede(old_id, GenericRecord(rid, new_text, created_at))
        return rid
