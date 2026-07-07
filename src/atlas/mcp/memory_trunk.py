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

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.memory.memory_index import ShreddedContentError, SqliteMemoryIndex, WriteGate
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
        self,
        text: str,
        *,
        record_id: str | None = None,
        record_type: str | None = None,
        memory_class: str = "factual",
    ) -> str:
        """Recuerda `text`. Devuelve el id (generado si no se da)."""
        rid = record_id if record_id is not None else uuid.uuid4().hex
        created_at = str(time.time_ns())
        provenance = hashlib.sha256(f"{text}{created_at}".encode()).hexdigest()
        self._index.upsert(
            GenericRecord(rid, text, created_at, record_type),
            merkle_leaf_hash=provenance,
            memory_class=memory_class,
        )
        return rid

    def add_from_knowledge_src(
        self, text: str, *, record_id: str | None = None, record_type: str | None = None
    ) -> str:
        """Recuerda conocimiento de `knowledge-src` como factual."""
        return self.add(text, record_id=record_id, record_type=record_type, memory_class="factual")

    def add_from_user_preference(
        self, text: str, *, record_id: str | None = None, record_type: str | None = None
    ) -> str:
        """Recuerda una preferencia declarada por el usuario como personal."""
        return self.add(text, record_id=record_id, record_type=record_type, memory_class="personal")

    def recall(self, query: str, k: int = 5) -> list[RecallHit]:
        """Devuelve hasta `k` candidatos VIGENTES ordenados por relevancia, con
        texto y procedencia. OJO: devuelve candidatos aunque ninguno supere el
        umbral — mira `matched` para distinguir un acierto real del ruido top-k.
        Lista vacía solo si el índice está vacío."""
        results = self._index.recall_all(query, k=k)
        hits: list[RecallHit] = []
        for r in results:
            try:
                text = self._index.text_of(r.lesson_id)
            except ShreddedContentError:
                continue
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

    def recall_multihop(self, query: str, *, hops: int = 2) -> list[RecallHit]:
        """Encadena recalls hasta `hops` saltos semánticos. Cada salto parte del
        texto del hit anterior como nueva query. Devuelve la cadena ordenada (sin
        repeticiones), saltando hits shredded o sin texto."""
        results = self._index.recall_multihop(query, hops=hops)
        hits: list[RecallHit] = []
        for r in results:
            try:
                text = self._index.text_of(r.lesson_id)
            except ShreddedContentError:
                continue
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

    def shred(self, record_id: str) -> None:
        """Destruye irreversiblemente el contenido de `record_id` (derecho al olvido).
        Propaga `KeyError` si el id no existe."""
        self._index.shred(record_id)

    def supersede(self, old_id: str, new_text: str, *, record_id: str | None = None) -> str:
        """`new_text` reemplaza a `old_id`: la vieja caduca (auditable, no se
        borra) y la nueva entra vigente con lineage. Genera procedencia igual
        que `add` (sha256 de text+created_at) para satisfacer WriteGate activos.
        Devuelve el id nuevo."""
        rid = record_id if record_id is not None else uuid.uuid4().hex
        created_at = str(time.time_ns())
        provenance = hashlib.sha256(f"{new_text}{created_at}".encode()).hexdigest()
        self._index.supersede(
            old_id,
            GenericRecord(rid, new_text, created_at),
            merkle_leaf_hash=provenance,
        )
        return rid

    def close(self) -> None:
        """Cierra el índice subyacente."""
        self._index.close()


class MemoryTrunkRouter:
    """Enruta cada tenant a su MemoryTrunk sobre un índice tenant-scoped (mismo db_path).
    Cachea por tenant. Aísla: el trunk de A nunca ve memorias de B."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        embedder: Any = None,
        threshold: float = 0.8,
        merkle: Any = None,
        auto_touch: bool = False,
        write_gate: "WriteGate | None" = None,
    ) -> None:
        self._db_path = Path(db_path)
        # Si no se provee embedder, crea uno compartido para que todos los tenants
        # usen la misma dimensión (distinta dim rompería el guard del índice).
        if embedder is None:
            from atlas.memory.embeddings import default_embedder

            # Gobernado por env (ATLAS_EMBEDDER=fastembed → semántico local; default stub).
            # Compartido entre tenants → misma dimensión (el guard del índice la exige).
            embedder = default_embedder()
        self._embedder = embedder
        self._threshold = threshold
        self._merkle = merkle
        self._auto_touch = auto_touch
        self._write_gate = write_gate
        self._trunks: dict[str, MemoryTrunk] = {}

    def for_tenant(self, tenant_id: str) -> MemoryTrunk:
        """Devuelve el MemoryTrunk para `tenant_id`, creándolo si no existe.
        Lanza ValueError si tenant_id está vacío o es solo whitespace."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError(f"tenant_id no puede ser vacío: {tenant_id!r}")
        if tenant_id not in self._trunks:
            index = SqliteMemoryIndex(
                self._db_path,
                tenant=tenant_id,
                embedder=self._embedder,
                threshold=self._threshold,
                merkle=self._merkle,
                auto_touch=self._auto_touch,
                write_gate=self._write_gate,
            )
            self._trunks[tenant_id] = MemoryTrunk(index)
        return self._trunks[tenant_id]

    def close(self) -> None:
        """Cierra el índice de cada trunk cacheado."""
        for trunk in self._trunks.values():
            trunk.close()
        self._trunks.clear()
