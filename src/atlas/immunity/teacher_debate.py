"""
Atlas Core — Debate con el maestro: corroboración / contradicción de propuestas LLM.

El maestro (cualquier LLM externo) propone lecciones; este módulo las coteja
contra los priores VERIFICADOS que ya residen en LessonStore. El valor central
es que el sistema puede CONTRADECIR al maestro en vez de absorberlo ciegamente:
si existe una lección verificada y en cadena que choca con la propuesta, el prior
gana. El maestro no tiene confianza ciega.

Capacidades honestas y límites:
- La detección de contradicción es heurística (similitud de embedding + postura).
  NO es prueba semántica formal; los falsos negativos con vocabulario dispar
  son esperados (la misma limitación que LessonRecaller documenta).
- No se entrenan pesos: se acumula conocimiento verificable, model-agnostic.
  Cualquier LLM puede ser maestro; ninguno puede sobrescribir priores sin pasar
  el verifier.
- El verifier conservador rechaza lecciones "allow" novel por seguridad: una
  propuesta de permitir algo nuevo no tiene cómo ser corroborada sin revisión
  humana o un gate externo explícito. Las "avoid" novel se auto-aceptan si el
  verifier por defecto las pasa (avoid_pattern no vacío), porque añadir una
  restricción es conservador por naturaleza.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from atlas.core.lesson_store import Lesson, LessonProvenance

if TYPE_CHECKING:
    from atlas.core.lesson_store import LessonStore
    from atlas.immunity.lesson_recaller import Recaller


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LessonProposal:
    """Propuesta de lección proveniente de un maestro (LLM externo).

    stance: "avoid" (el patrón es peligroso, evitar) o "allow" (el patrón
    era un falso positivo, se debe permitir). Las propuestas "allow" novel
    son rechazadas por el verifier conservador por defecto.
    """

    detection_heuristic: str
    avoid_pattern: str
    stance: str  # "avoid" | "allow"
    rationale: str
    teacher_id: str  # procedencia: identifica al LLM que propone


class DebateOutcome(str, Enum):
    CORROBORATED = "corroborated"    # la propuesta confirma un prior verificado
    CONTRADICTED = "contradicted"    # la propuesta choca con un prior; se descarta
    ACCEPTED_NEW = "accepted_new"    # novel + verifier OK; se persiste
    REJECTED = "rejected"            # novel pero verifier rechaza


@dataclass(frozen=True)
class DebateResult:
    outcome: DebateOutcome
    matched_lesson_id: str | None   # id de la lección del prior con mayor similitud
    score: float                    # similitud coseno con el prior casado (0 si novel)
    reason: str                     # explicación legible
    lesson_id: str | None           # id de la lección CREADA si ACCEPTED_NEW


# ---------------------------------------------------------------------------
# Helper: leer postura de una lección desde sus tags
# ---------------------------------------------------------------------------


def _lesson_stance(lesson: Lesson) -> str:
    """Lee la postura de una lección desde sus tags ("stance:X").

    Si no hay tag de stance se asume "avoid": todas las lecciones históricas
    son restricciones (la convención por defecto del sistema).
    """
    for tag in lesson.tags:
        if tag.startswith("stance:"):
            return tag[len("stance:"):]
    return "avoid"


# ---------------------------------------------------------------------------
# Verifier conservador por defecto
# ---------------------------------------------------------------------------


def _default_verifier(proposal: LessonProposal) -> bool:
    """Verifier conservador para propuestas novel (sin match en el store).

    Reglas:
    - stance "avoid" con avoid_pattern no vacío → acepta. Añadir una
      restricción es la postura más segura y no requiere gate adicional.
    - stance "allow" → rechaza siempre. Permitir algo nuevo no verificado
      desde un LLM externo es arriesgado; requiere arbitraje explícito.
    - Cualquier otra stance → rechaza (defensa ante valores inesperados).
    """
    if proposal.stance == "avoid" and proposal.avoid_pattern.strip():
        return True
    return False


# ---------------------------------------------------------------------------
# TeacherDebate
# ---------------------------------------------------------------------------


class TeacherDebate:
    """Árbitro que media entre las propuestas del maestro y el corpus verificado.

    El flujo de consider():
        1. Reindexar el recaller (captura lecciones recién añadidas).
        2. Buscar el prior más similar al texto representativo de la propuesta.
        3a. Match (score >= sim_threshold):
            - Misma postura → CORROBORATED (no duplica).
            - Postura opuesta → CONTRADICTED (el prior gana; no se muta el store).
        3b. Sin match (novel):
            - verifier(proposal) → True: construir Lesson y persistir → ACCEPTED_NEW.
            - verifier(proposal) → False: REJECTED.
    """

    def __init__(
        self,
        store: LessonStore,
        recaller: Recaller,
        *,
        sim_threshold: float = 0.8,
        verifier: Callable[[LessonProposal], bool] | None = None,
    ) -> None:
        self._store = store
        self._recaller = recaller
        self._sim_threshold = sim_threshold
        self._verifier: Callable[[LessonProposal], bool] = (
            verifier if verifier is not None else _default_verifier
        )

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------

    def consider(self, proposal: LessonProposal) -> DebateResult:
        """Evalúa una propuesta del maestro y devuelve el resultado del debate."""
        # 1. Asegurar índice fresco (incluye lecciones añadidas en esta sesión)
        self._recaller.index()

        # Texto representativo de la propuesta (mismo orden que LessonRecaller usa)
        query_text = proposal.avoid_pattern + " " + proposal.detection_heuristic

        # 2. Buscar prior
        recall = self._recaller.recall(query_text)

        if recall is not None and recall.matched and recall.score >= self._sim_threshold:
            # 3a. Hay match — cotejar posturas
            prior = self._store.get(recall.lesson_id)
            prior_stance = _lesson_stance(prior) if prior is not None else "avoid"

            if prior_stance == proposal.stance:
                return DebateResult(
                    outcome=DebateOutcome.CORROBORATED,
                    matched_lesson_id=recall.lesson_id,
                    score=recall.score,
                    reason=(
                        f"La propuesta confirma la lección verificada '{recall.lesson_id}' "
                        f"(score={recall.score:.3f}, stance='{proposal.stance}'). "
                        "No se crea lección duplicada; el prior ya está en cadena."
                    ),
                    lesson_id=None,
                )
            else:
                return DebateResult(
                    outcome=DebateOutcome.CONTRADICTED,
                    matched_lesson_id=recall.lesson_id,
                    score=recall.score,
                    reason=(
                        f"La propuesta del maestro (stance='{proposal.stance}') contradice "
                        f"la lección verificada '{recall.lesson_id}' "
                        f"(stance='{prior_stance}', score={recall.score:.3f}). "
                        "El prior verificado gana sobre el maestro. "
                        "Para revertirlo se requiere arbitraje explícito."
                    ),
                    lesson_id=None,
                )

        # 3b. Novel — pasar por el verifier
        if not self._verifier(proposal):
            return DebateResult(
                outcome=DebateOutcome.REJECTED,
                matched_lesson_id=recall.lesson_id if recall is not None else None,
                score=recall.score if recall is not None else 0.0,
                reason=(
                    f"Propuesta novel del maestro '{proposal.teacher_id}' rechazada "
                    f"por el verifier (stance='{proposal.stance}'). "
                    "Las propuestas 'allow' novel no se auto-aceptan sin gate explícito."
                ),
                lesson_id=None,
            )

        # Verifier OK — construir y persistir la lección
        new_id = f"teach-{uuid.uuid4().hex[:8]}"
        new_lesson = Lesson(
            id=new_id,
            title=f"[{proposal.teacher_id}] {proposal.detection_heuristic[:60]}",
            provenance=LessonProvenance.EXTERNAL_SOURCE,
            detection_heuristic=proposal.detection_heuristic,
            avoid_pattern=proposal.avoid_pattern,
            evidence={
                "verdict": "pass",
                "stance": proposal.stance,
                "teacher_id": proposal.teacher_id,
                "rationale": proposal.rationale,
            },
            tags=(
                f"stance:{proposal.stance}",
                f"teacher:{proposal.teacher_id}",
            ),
        )
        self._store.add(new_lesson)
        # Reindexar para que debate_batch encuentre esta lección en la siguiente llamada
        self._recaller.index()

        return DebateResult(
            outcome=DebateOutcome.ACCEPTED_NEW,
            matched_lesson_id=None,
            score=recall.score if recall is not None else 0.0,
            reason=(
                f"Lección novel del maestro '{proposal.teacher_id}' aceptada "
                f"y persistida como '{new_id}' (stance='{proposal.stance}')."
            ),
            lesson_id=new_id,
        )

    def debate_batch(self, proposals: list[LessonProposal]) -> list[DebateResult]:
        """Evalúa una lista de propuestas en orden.

        El estado del store evoluciona entre propuestas: una propuesta ACCEPTED_NEW
        en la posición N es visible para las propuestas N+1..M.
        """
        return [self.consider(p) for p in proposals]
