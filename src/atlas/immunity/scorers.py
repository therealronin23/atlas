"""
Atlas Immunity — RecallAffinityScorer: afinidad por cobertura sobre ataques de test.

Mide qué fracción de test_attacks un ImmunityCandidate reconoce, usando
similitud coseno entre embeddings.

Límites honestos obligatorios:
  - La afinidad mide COBERTURA sobre el set de test DADO, no robustez general.
    Un score alto solo indica que el candidato cubre bien ese set específico.
  - La calidad del score depende enteramente del embedder:
      · StubEmbedder (default): similitud léxica-ish basada en hash de tokens.
        Funciona para tests y arranque sin keys externas. Paráfrasis con
        vocabulario distinto → score bajo (limitación documentada).
      · Embedder real (LiteLLMEmbedder): similitud semántica real; requiere key.
  - Candidatos con avoid_pattern/detection_heuristic vacíos → similitud 0 con
    todo; el score refleja ausencia de señal, no robustez.

Dependencias: stdlib + atlas.memory.embeddings + atlas.security.drift.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.security.drift import cosine_distance

if TYPE_CHECKING:
    from atlas.immunity.affinity_maturation import ImmunityCandidate


# ---------------------------------------------------------------------------
# RecallAffinityScorer
# ---------------------------------------------------------------------------


class RecallAffinityScorer:
    """
    Implementa el Protocol AffinityScorer de affinity_maturation.py.

    Puntúa un ImmunityCandidate comparando su representación embebida
    (avoid_pattern + ' ' + detection_heuristic) contra cada test_attack:
    un ataque se considera "reconocido" si la similitud coseno supera
    el umbral configurado. El score final es la fracción de ataques
    reconocidos sobre el total.

    Uso::

        scorer = RecallAffinityScorer()
        s = scorer.score(candidate, ["eval(user_input)", "exec(__import__)"])
    """

    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
    ) -> None:
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold debe estar en [0, 1], recibido {threshold}")
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    @staticmethod
    def _candidate_text(candidate: ImmunityCandidate) -> str:
        """Texto representativo del candidato (mismo esquema que LessonRecaller)."""
        parts = [candidate.avoid_pattern, candidate.detection_heuristic]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Similitud coseno en [0, 1] = 1 - cosine_distance."""
        return max(0.0, min(1.0, 1.0 - cosine_distance(a, b)))

    def score(self, candidate: ImmunityCandidate, test_attacks: list[str]) -> float:
        """
        Devuelve fracción de test_attacks reconocidos por el candidato.

        - Lista vacía → 0.0 (sin información, sin excepción).
        - Determinista con StubEmbedder (misma entrada → mismo resultado).
        - Rango: [0.0, 1.0].
        """
        if not test_attacks:
            return 0.0

        cand_text = self._candidate_text(candidate)
        if not cand_text.strip():
            return 0.0

        cand_vec = self._embedder.embed(cand_text)
        attack_vecs = self._embedder.embed_batch(test_attacks)

        recognized = sum(
            1
            for av in attack_vecs
            if self._cosine_similarity(cand_vec, av) >= self._threshold
        )
        return recognized / len(test_attacks)
