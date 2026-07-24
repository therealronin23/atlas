"""Loop inmune en vivo (gated) — cosecha lecciones de escaladas reales.

Cierra el lazo "exposición → lección registrada" SIN acoplar el hot-path del
gateway: el gateway solo emite un callback opt-in `on_escalation(payload, cause)`
cuando una sesión escala (hay causa). Este recorder recibe ese evento y lo
arbitra contra los priores verificados vía :class:`TeacherDebate` (corrobora /
acepta-como-nueva / contradice / rechaza), anclando todo en la cadena.

Privacidad (I3): solo se procesa contenido de peticiones ESCALADAS (con causa
registrada) — nunca tráfico legítimo, que jamás dispara el hook. Persistir el
patrón de un ataque con causa es justamente la inspección-acotada de OSM-028, no
perfilado. El gate (el verificador del TeacherDebate) decide qué entra.

Límites honestos: el recorder no auto-MITIGA (no bloquea tráfico por su cuenta);
solo acumula memoria auditable. Aplicar una lección para bloquear es una decisión
separada y gated. La calidad del patrón depende del contenido escalado disponible.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas.immunity.teacher_debate import DebateOutcome, LessonProposal

if TYPE_CHECKING:
    from atlas.core.inference_hub import InferenceHub
    from atlas.immunity.teacher_debate import DebateResult, TeacherDebate

_JUDGE_PROMPT = (
    "Eres el juez de un sistema inmune que decide si un patrón ESCALADO por "
    "un detector de deriva de sesión merece recordarse como amenaza real, o "
    "si probablemente es el prompt legítimo pero inusual de tu único "
    "operador (sistema de un solo usuario, no un producto multi-tenant). "
    "Responde en la PRIMERA línea SOLO 'YES' (patrón hostil real, memorizar "
    "como avoid) o 'NO' (probablemente falso positivo / prompt legítimo). "
    "Luego, una línea con la razón.\n\n"
    "CAUSA DE LA ESCALADA: {cause}\n"
    "PATRÓN ESCALADO:\n{pattern}\n"
)

_PENDING_REVIEW_OUTCOMES = (DebateOutcome.REJECTED, DebateOutcome.CONTRADICTED)


def build_judge_verifier(hub: "InferenceHub") -> Callable[[LessonProposal], bool]:
    """Verifier gateado por un juez LLM real, para el path de escalada EN VIVO.

    Sustituye al verifier permisivo por defecto de TeacherDebate (que acepta
    CUALQUIER avoid_pattern no vacío) — ese default está bien para debate
    offline/batch, pero un sistema de un solo usuario no debe memorizar como
    "amenaza" cada prompt inusual propio sin que algo lo revise primero
    (Cónclave 2026-07-24, hallazgo: "envenena el aprendizaje").

    Fail-closed en dos sentidos, igual que el resto de la casa:
    - stance "allow" novel: rechazada SIN llamar al juez (mismo invariante
      que el verifier por defecto, y no gasta una llamada LLM en un caso ya
      decidido).
    - Juez no disponible / respuesta ilegible: rechazada (NO auto-acepta a
      ciegas). El caller (GatedLessonRecorder) enruta el rechazo a
      pending_review — nunca desaparece en silencio.
    """
    def _verify(proposal: LessonProposal) -> bool:
        if proposal.stance != "avoid" or not proposal.avoid_pattern.strip():
            return False
        from atlas.core.inference_hub import InferenceRequest, InferenceLevel

        resp = hub.infer(InferenceRequest(
            prompt=_JUDGE_PROMPT.format(
                cause=proposal.detection_heuristic, pattern=proposal.avoid_pattern,
            ),
            level=InferenceLevel.L0,
        ))
        if not resp.success or not resp.text.strip():
            return False
        first_line = resp.text.strip().splitlines()[0].strip().upper()
        return first_line.startswith("YES")

    return _verify


class GatedLessonRecorder:
    """Convierte escaladas en vivo en lecciones arbitradas (gated).

    Lo que el debate ACEPTA (corroborated/accepted_new) se persiste como
    siempre. Lo que RECHAZA (rejected/contradicted) ya no desaparece en
    silencio: si se da `pending_review_path`, queda anotado ahí para que la
    próxima auditoría completa lo revise (Cónclave 2026-07-24)."""

    def __init__(
        self,
        debate: "TeacherDebate",
        *,
        source_id: str = "live-escalation",
        pending_review_path: Path | None = None,
    ) -> None:
        self._debate = debate
        self._source_id = source_id
        self._pending_review_path = pending_review_path

    def record(self, payload: bytes, cause: str) -> "DebateResult":
        """Arbitra una escalada (payload + causa) contra los priores."""
        text = payload.decode("utf-8", errors="replace")
        proposal = LessonProposal(
            detection_heuristic=cause or "live escalation",
            avoid_pattern=text,
            stance="avoid",
            rationale="harvested from a live, cause-flagged escalation",
            teacher_id=self._source_id,
        )
        result = self._debate.consider(proposal)
        if self._pending_review_path is not None and result.outcome in _PENDING_REVIEW_OUTCOMES:
            self._append_pending_review(proposal, result, cause)
        return result

    def _append_pending_review(
        self, proposal: LessonProposal, result: "DebateResult", cause: str,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cause": cause,
            "outcome": result.outcome.value,
            "reason": result.reason,
            "detection_heuristic": proposal.detection_heuristic,
            "avoid_pattern": proposal.avoid_pattern,
            "teacher_id": proposal.teacher_id,
        }
        assert self._pending_review_path is not None
        self._pending_review_path.parent.mkdir(parents=True, exist_ok=True)
        with self._pending_review_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def as_hook(self) -> Callable[[bytes, str], None]:
        """Devuelve un callable apto para ``gateway.call(on_escalation=...)``.

        Descarta el DebateResult (el gateway no lo necesita); el resultado queda
        en el store/cadena. Mantiene el gateway desacoplado: solo recibe un
        Callable, nunca importa esta capa.
        """
        def _hook(payload: bytes, cause: str) -> None:
            self.record(payload, cause)

        return _hook
