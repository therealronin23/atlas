"""
Atlas Immunity — Afinidad Maduración (ADR-054 capa 5).

Implementa hipermutación somática + selección clonal sobre candidatos de defensa:

    bypass detectado / ataque externo
         ↓
    ImmunityCandidate inicial (desde LessonStore)
         ↓
    hypermutate() — LLM genera variantes semánticas (no ruido de palabra-inversión)
         ↓
    score() — AffinityScorer puntúa cada variante contra ataques de test
         ↓
    mature() — selección clonal + aprobación via Decider (I5, tier LOW)
         ↓
    población promovida → lista para integrar en VerifiedProducer

Invariante I5 (ADR-054): la promoción pasa por el Decider. En modo autónomo
(tier=LOW, sin cambio en superficie de rechazo) se auto-aprueba; tier=MEDIUM+
requiere revisión explícita. Este módulo siempre promueve tier=LOW porque los
candidatos son *variantes* de reglas ya aprobadas, no reglas nuevas de rechazo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atlas.core.decider import Allow, DecisionAction


@runtime_checkable
class DeciderProtocol(Protocol):
    """Tipado para Decider sin circular import en runtime."""

    def decide(
        self,
        action: object,
        *,
        sanctioned_intent: str,
        context: dict[str, object],
    ) -> object:
        """Devuelve Allow u otra Decision."""
        ...


@dataclass
class ImmunityCandidate:
    """Variante de una lección de defensa en el ciclo de maduración."""

    id: str
    avoid_pattern: str
    detection_heuristic: str
    affinity_score: float = 0.0
    generation: int = 0
    parent_id: str | None = None
    mutation_rate: float = 0.15  # decrece generación a generación

    @classmethod
    def from_lesson(cls, lesson_id: str, avoid_pattern: str, detection_heuristic: str) -> "ImmunityCandidate":
        return cls(
            id=str(uuid.uuid4()),
            avoid_pattern=avoid_pattern,
            detection_heuristic=detection_heuristic,
            parent_id=lesson_id,
        )


@runtime_checkable
class AffinityScorer(Protocol):
    """Puntúa qué tan bien un candidato detecta los ataques de test."""

    def score(self, candidate: ImmunityCandidate, test_attacks: list[str]) -> float:
        """Devuelve puntuación normalizada 0.0–1.0."""
        ...


@runtime_checkable
class TextMutator(Protocol):
    """Genera una variante semántica de un texto de defensa."""

    def mutate(self, text: str) -> str:
        """Devuelve una paráfrasis semánticamente equivalente con diversidad léxica."""
        ...


class AffinityMaturation:
    """
    Motor de hipermutación somática + selección clonal para reglas de defensa.

    La mutación es semántica (vía LLM), no ruido léxico — word[::-1] y 'anti_'+word
    generan tokens que no guardan relación con la semántica de defensa y producen
    candidatos inútiles. La mutación real repara el problema que CHASE (arXiv:2606.05523)
    identifica: el auto-juego colapsa en diversidad; la inyección de variantes
    semánticas genuinas mantiene la exploración del espacio de ataque.
    """

    def __init__(
        self,
        scorer: AffinityScorer,
        mutator: TextMutator,
        decider: DeciderProtocol,
        max_population: int = 30,
    ) -> None:
        self._scorer = scorer
        self._mutator = mutator
        self._decider = decider
        self._max_population = max_population
        self.population: list[ImmunityCandidate] = []

    def add_candidate(self, candidate: ImmunityCandidate) -> None:
        self.population.append(candidate)

    def hypermutate(self, candidate: ImmunityCandidate, num_clones: int = 8) -> list[ImmunityCandidate]:
        """Genera clones con mutación semántica via TextMutator."""
        clones: list[ImmunityCandidate] = []
        for i in range(num_clones):
            clone = ImmunityCandidate(
                id=f"{candidate.id}_g{candidate.generation + 1}_{i}",
                avoid_pattern=self._mutator.mutate(candidate.avoid_pattern),
                detection_heuristic=self._mutator.mutate(candidate.detection_heuristic),
                generation=candidate.generation + 1,
                parent_id=candidate.id,
                mutation_rate=candidate.mutation_rate * 0.85,
            )
            clones.append(clone)
        return clones

    def mature(
        self,
        test_attacks: list[str],
        num_clones: int = 8,
        min_affinity: float = 0.65,
        max_promoted: int = 5,
    ) -> list[ImmunityCandidate]:
        """
        Ciclo completo: hipermutación → scoring → selección clonal → Decider.
        Devuelve los candidatos aprobados para promover.
        """
        if not self.population:
            return []

        new_candidates: list[ImmunityCandidate] = []
        for candidate in list(self.population):
            clones = self.hypermutate(candidate, num_clones=num_clones)
            for clone in clones:
                clone.affinity_score = self._scorer.score(clone, test_attacks)
            new_candidates.extend(clones)

        # Selección clonal: solo los que superan el umbral de afinidad
        promoted_candidates = sorted(
            [c for c in new_candidates if c.affinity_score >= min_affinity],
            key=lambda c: c.affinity_score,
            reverse=True,
        )[:max_promoted]

        approved: list[ImmunityCandidate] = []
        for candidate in promoted_candidates:
            # I5 (ADR-054): pasar por Decider, tier=LOW (variante sin cambio en superficie)
            try:
                from atlas.core.decider import Allow, DecisionAction
                action = DecisionAction(
                    kind="immunity_candidate_promotion",
                    requires_approval=False,  # tier LOW: reversible, sin cambio en superficie de rechazo
                    mutating=False,
                    reversible=True,
                )
                decision = self._decider.decide(
                    action,
                    sanctioned_intent="promote_immunity_candidate",
                    context={
                        "candidate_id": candidate.id,
                        "affinity_score": candidate.affinity_score,
                        "generation": candidate.generation,
                        "tier": "LOW",
                    },
                )
                if isinstance(decision, Allow):
                    approved.append(candidate)
            except Exception:
                # fail-closed: si el Decider falla, no se promueve
                pass

        # Merge en población + recortar por tamaño máximo
        self.population.extend(approved)
        self.population.sort(key=lambda c: c.affinity_score, reverse=True)
        self.population = self.population[: self._max_population]

        return approved
