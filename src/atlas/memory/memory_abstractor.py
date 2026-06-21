"""
Atlas Core — MemoryAbstractor: ejemplos → patrones, genérico (MOTOR, agnóstico).

Agrupa cualquier `MemoryRecord` en PATRONES (clases abstractas) y recuerda sobre
el CENTROIDE del patrón, no sobre el string crudo. Es el motor de abstracción de
dominio neutro; la memoria inmune (`PatternAbstractor`) lo COMPONE adaptando
`Lesson` → `MemoryRecord`.

Clustering DETERMINISTA por umbral de coseno (greedy aglomerativo, 1 pasada, sin
deps): mismo corpus → mismos patrones, ids direccionados por contenido.

LÍMITE HONESTO: agrupa reformulaciones/vecinos, NO descubre la estructura "real"
de familias. La prueba de si esto GENERALIZA es el experimento de held-out (1c),
no este módulo.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from collections.abc import Iterable

from atlas.immunity.lesson_recaller import _cosine_similarity
from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.record import MemoryRecord


@dataclass(frozen=True)
class Pattern:
    """Clase abstracta aprendida a partir de >=1 registro.

    id: direccionado por contenido (hash de member_ids ordenados) → estable.
    label: texto del ejemplo más cercano al centroide (representante auditable).
    centroid: media L2-normalizada de los vectores de los miembros.
    family: opcional, para held-out en 1c (taxonomía externa).
    """

    id: str
    label: str
    centroid: list[float]
    member_ids: tuple[str, ...]
    n_examples: int
    family: str | None = None


@dataclass(frozen=True)
class PatternMatch:
    pattern_id: str
    score: float
    matched: bool


@dataclass
class _Bucket:
    member_ids: list[str] = field(default_factory=list)
    vectors: list[list[float]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    centroid: list[float] = field(default_factory=list)

    def add(self, record_id: str, vec: list[float], text: str) -> None:
        self.member_ids.append(record_id)
        self.vectors.append(vec)
        self.texts.append(text)
        self.centroid = _mean_normalized(self.vectors)


def _mean_normalized(vectors: list[list[float]]) -> list[float]:
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    n = len(vectors)
    mean = [x / n for x in acc]
    norm = math.sqrt(sum(x * x for x in mean))
    if norm == 0.0:
        return mean
    return [x / norm for x in mean]


class MemoryAbstractor:
    """Agrupa registros en patrones y recuerda sobre sus centroides."""

    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
        cluster_threshold: float | None = None,
        recall_threshold: float | None = None,
    ) -> None:
        """`threshold` es el default de ambos umbrales; sepáralos para evitar el
        confound de 1c (agrupar fino vs reconocer laxo son decisiones distintas):
        - `cluster_threshold`: cómo de apretado se agrupan ejemplos en un patrón.
        - `recall_threshold`: cómo de cerca debe estar una query para contar match.
        """
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._cluster_threshold = cluster_threshold if cluster_threshold is not None else threshold
        self._recall_threshold = recall_threshold if recall_threshold is not None else threshold
        self._patterns: list[Pattern] = []
        self._assignment: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Abstracción (clustering determinista de una pasada)
    # ------------------------------------------------------------------

    def abstract(self, records: Iterable[MemoryRecord]) -> list[Pattern]:
        """Agrupa los registros en patrones. Idempotente: reemplaza el estado."""
        buckets: list[_Bucket] = []
        for record in records:
            text = record.text
            vec = self._embedder.embed(text)
            best: _Bucket | None = None
            best_score = -1.0
            for b in buckets:
                score = _cosine_similarity(vec, b.centroid)
                if score > best_score:
                    best_score = score
                    best = b
            if best is not None and best_score >= self._cluster_threshold:
                best.add(record.record_id, vec, text)
            else:
                nb = _Bucket()
                nb.add(record.record_id, vec, text)
                buckets.append(nb)

        self._patterns = [self._finalize(b) for b in buckets]
        self._assignment = {mid: p.id for p in self._patterns for mid in p.member_ids}
        return self._patterns

    def _finalize(self, bucket: _Bucket) -> Pattern:
        member_ids = tuple(bucket.member_ids)
        pid = "pat-" + hashlib.sha256(
            "|".join(sorted(member_ids)).encode("utf-8")
        ).hexdigest()[:12]
        best_i = 0
        best_score = -1.0
        for i, v in enumerate(bucket.vectors):
            s = _cosine_similarity(v, bucket.centroid)
            if s > best_score:
                best_score = s
                best_i = i
        return Pattern(
            id=pid,
            label=bucket.texts[best_i],
            centroid=list(bucket.centroid),
            member_ids=member_ids,
            n_examples=len(member_ids),
        )

    def assignment(self) -> dict[str, str]:
        """Mapa record_id → pattern_id del último `abstract()` (lineage)."""
        return dict(self._assignment)

    @property
    def patterns(self) -> list[Pattern]:
        return list(self._patterns)

    # ------------------------------------------------------------------
    # Recall sobre patrones
    # ------------------------------------------------------------------

    def recall(self, query_text: str) -> PatternMatch | None:
        if not self._patterns:
            return None
        results = self.recall_all(query_text, k=1)
        return results[0] if results else None

    def recall_all(self, query_text: str, k: int = 5) -> list[PatternMatch]:
        if not self._patterns:
            return []
        if not query_text.strip():
            return [
                PatternMatch(pattern_id=p.id, score=0.0, matched=False)
                for p in self._patterns
            ][:k]
        query_vec = self._embedder.embed(query_text)
        results = [
            PatternMatch(
                pattern_id=p.id,
                score=_cosine_similarity(query_vec, p.centroid),
                matched=_cosine_similarity(query_vec, p.centroid) >= self._recall_threshold,
            )
            for p in self._patterns
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]
