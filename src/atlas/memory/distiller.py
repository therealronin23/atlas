"""
Atlas Core — MemoryDistiller (ADR-018, Gate D)

Compresion semantica de contexto antes de invocar al InferenceHub.
Objetivo: reducir tokens enviados a proveedores L1/L2 manteniendo la
informacion esencial para la tarea actual.

Estrategia v1 (sin LLM secundario):
  1. Los chunks marcados como ChunkSource.SYSTEM se preservan SIEMPRE
     y no consumen del budget compresivo (son axiomaticos).
  2. El resto se ranquea por cosine similarity contra el embedding del
     query y se admiten en orden de score descendente mientras quepan
     en el budget. Empates de score se rompen por timestamp (mas
     reciente gana).
  3. El output respeta el orden conceptual:
        [system chunks] -> [seleccionados por relevancia] -> [recent]

Conexion con D4: si se pasa un KuzuVectorStore, gather_relevant() puede
extraer Patterns/Failures/Evidence ya pre-indexados.

Conexion con D1: el output de build_context() puede pasarse como
InferenceRequest.context al InferenceHub.

ADR-018 marca esto como pre-step mandatorio antes de cualquier L1/L2.
El cableo automatico al Orchestrator (interceptar handle_intent) queda
como follow-up cuando el pipeline de inferencia este consumido por
mas codigo del sistema.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from atlas.memory.embeddings import Embedder
from atlas.memory.vector_store import cosine_similarity

if TYPE_CHECKING:
    from atlas.memory.vector_store import KuzuVectorStore


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


class ChunkSource(str, Enum):
    """Categoria del chunk. SYSTEM y RECENT reciben trato especial."""

    SYSTEM        = "system"        # Constitucion, vision, reglas. Siempre se incluyen.
    RECENT        = "recent"        # Conversacion / historial inmediato. Se preserva al final.
    PATTERN       = "pattern"       # Patron aprobado.
    FAILURE       = "failure"       # Fallo registrado.
    EVIDENCE      = "evidence"      # Evidencia / observacion.
    NOTE          = "note"          # Otros (notas, tool outputs, etc.).


@dataclass(frozen=True)
class Chunk:
    """Unidad de contexto candidata a entrar al prompt."""

    text: str
    source: ChunkSource = ChunkSource.NOTE
    tokens: int = 0                # 0 = se estima al vuelo
    timestamp: str = ""            # ISO; "" si no aplica
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DistillationResult:
    """Resultado de distill(): chunks ordenados + auditoria."""

    chunks: tuple[Chunk, ...]
    total_tokens: int
    budget: int
    discarded_count: int
    strategy: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """
    Estimacion conservadora de tokens.
    Heuristica: ceil(len(text) / 4). Suficiente como aproximacion para
    presupuestar. Si en el futuro se necesita precision por modelo, se
    cablea tiktoken (ya viene transitivamente con litellm).
    """
    if not text:
        return 0
    return math.ceil(len(text) / 4)


# ---------------------------------------------------------------------------
# Distiller
# ---------------------------------------------------------------------------


class MemoryDistiller:
    """
    Comprime un set de chunks segun budget de tokens y relevancia al query.

    Uso minimo:

        distiller = MemoryDistiller(embedder=StubEmbedder())
        result = distiller.distill(
            query="como debuggeo un timeout en hermes",
            chunks=[Chunk(text=..., source=ChunkSource.PATTERN), ...],
        )
        context_text = "\\n\\n".join(c.text for c in result.chunks)

    Con KuzuVectorStore conectado:

        distiller = MemoryDistiller(embedder, vector_store=store)
        ctx = distiller.build_context(
            query="timeout hermes",
            system_chunks=["constitucion..."],
            recent_chunks=["ultima interaccion..."],
        )
    """

    DEFAULT_TARGET_TOKENS = 2000

    def __init__(
        self,
        embedder: Embedder,
        *,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        vector_store: "KuzuVectorStore | None" = None,
    ) -> None:
        if target_tokens <= 0:
            raise ValueError(f"target_tokens debe ser positivo: {target_tokens}")
        self._embedder = embedder
        self._target_tokens = target_tokens
        self._vector_store = vector_store

    @property
    def target_tokens(self) -> int:
        return self._target_tokens

    # ------------------------------------------------------------------
    # Core: distill
    # ------------------------------------------------------------------

    def distill(
        self,
        query: str,
        chunks: list[Chunk],
        *,
        target_tokens: int | None = None,
    ) -> DistillationResult:
        budget = target_tokens if target_tokens is not None else self._target_tokens
        if budget <= 0:
            raise ValueError(f"budget debe ser positivo: {budget}")

        normalized = [self._with_tokens(c) for c in chunks]

        system: list[Chunk] = [c for c in normalized if c.source == ChunkSource.SYSTEM]
        recent: list[Chunk] = [c for c in normalized if c.source == ChunkSource.RECENT]
        scorable: list[Chunk] = [
            c for c in normalized
            if c.source not in (ChunkSource.SYSTEM, ChunkSource.RECENT)
        ]

        # 1. System chunks ocupan budget pero son axiomaticos: NUNCA se descartan
        used_tokens = sum(c.tokens for c in system)

        # 2. Recent: se preservan tambien (interaccion inmediata).
        used_tokens += sum(c.tokens for c in recent)

        # 3. Lo demas se ranquea y se admite mientras quepa
        ranked = self._rank_by_relevance(query, scorable)
        selected_scored: list[Chunk] = []
        discarded = 0
        for chunk, _score in ranked:
            if used_tokens + chunk.tokens <= budget:
                selected_scored.append(chunk)
                used_tokens += chunk.tokens
            else:
                discarded += 1

        # 4. Ensamblaje: system -> scorables priorizados -> recent
        final = tuple(system + selected_scored + recent)
        return DistillationResult(
            chunks=final,
            total_tokens=used_tokens,
            budget=budget,
            discarded_count=discarded,
            strategy="embed-rank-v1",
        )

    # ------------------------------------------------------------------
    # Extras: extraccion desde vector_store y ensamble end-to-end
    # ------------------------------------------------------------------

    def gather_relevant(
        self,
        query: str,
        *,
        max_patterns: int = 5,
        max_failures: int = 3,
        max_evidence: int = 0,
    ) -> list[Chunk]:
        """
        Extrae chunks relevantes del KuzuVectorStore si esta disponible.
        Devuelve [] si no hay vector_store.
        """
        if self._vector_store is None:
            return []

        out: list[Chunk] = []
        if max_patterns > 0:
            for p_hit in self._vector_store.find_similar_patterns(query, top_k=max_patterns):
                out.append(Chunk(
                    text=p_hit.text,
                    source=ChunkSource.PATTERN,
                    timestamp=p_hit.created_at,
                    metadata={"id": p_hit.id, "score": f"{p_hit.score:.4f}"},
                ))
        if max_failures > 0:
            for f_hit in self._vector_store.find_similar_failures(query, top_k=max_failures):
                out.append(Chunk(
                    text=f"{f_hit.error_type}: {f_hit.description}\nFix: {f_hit.solution}",
                    source=ChunkSource.FAILURE,
                    timestamp=f_hit.occurred_at,
                    metadata={"id": f_hit.id, "score": f"{f_hit.score:.4f}"},
                ))
        if max_evidence > 0:
            for e_hit in self._vector_store.find_similar_evidence(query, top_k=max_evidence):
                out.append(Chunk(
                    text=e_hit.text,
                    source=ChunkSource.EVIDENCE,
                    timestamp=e_hit.created_at,
                    metadata={"id": e_hit.id, "source": e_hit.source, "score": f"{e_hit.score:.4f}"},
                ))
        return out

    def build_context(
        self,
        query: str,
        *,
        system_chunks: list[str] | None = None,
        recent_chunks: list[str] | None = None,
        extra_chunks: list[Chunk] | None = None,
        target_tokens: int | None = None,
    ) -> tuple[str, DistillationResult]:
        """
        Ensamblaje end-to-end: extrae del vector_store, mezcla con system+recent,
        comprime al budget y devuelve un string listo para inyectar como contexto.
        """
        chunks: list[Chunk] = []
        for text in system_chunks or []:
            chunks.append(Chunk(text=text, source=ChunkSource.SYSTEM))
        chunks.extend(self.gather_relevant(query))
        for text in recent_chunks or []:
            chunks.append(Chunk(text=text, source=ChunkSource.RECENT))
        chunks.extend(extra_chunks or [])

        result = self.distill(query, chunks, target_tokens=target_tokens)
        text_blob = "\n\n".join(c.text for c in result.chunks)
        return text_blob, result

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _with_tokens(self, chunk: Chunk) -> Chunk:
        if chunk.tokens > 0:
            return chunk
        return Chunk(
            text=chunk.text,
            source=chunk.source,
            tokens=estimate_tokens(chunk.text),
            timestamp=chunk.timestamp,
            metadata=chunk.metadata,
        )

    def _rank_by_relevance(
        self, query: str, chunks: list[Chunk]
    ) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []
        qvec = self._embedder.embed(query)
        scored: list[tuple[Chunk, float]] = []
        for chunk in chunks:
            cvec = self._embedder.embed(chunk.text)
            score = cosine_similarity(qvec, cvec)
            scored.append((chunk, score))
        # Score descendente; empate -> timestamp mas reciente primero
        scored.sort(key=lambda t: (t[1], t[0].timestamp), reverse=True)
        return scored
