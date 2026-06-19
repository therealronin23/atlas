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

from collections.abc import Callable
from typing import TYPE_CHECKING

from atlas.immunity.teacher_debate import LessonProposal

if TYPE_CHECKING:
    from atlas.immunity.teacher_debate import DebateResult, TeacherDebate


class GatedLessonRecorder:
    """Convierte escaladas en vivo en lecciones arbitradas (gated)."""

    def __init__(self, debate: "TeacherDebate", *, source_id: str = "live-escalation") -> None:
        self._debate = debate
        self._source_id = source_id

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
        return self._debate.consider(proposal)

    def as_hook(self) -> Callable[[bytes, str], None]:
        """Devuelve un callable apto para ``gateway.call(on_escalation=...)``.

        Descarta el DebateResult (el gateway no lo necesita); el resultado queda
        en el store/cadena. Mantiene el gateway desacoplado: solo recibe un
        Callable, nunca importa esta capa.
        """
        def _hook(payload: bytes, cause: str) -> None:
            self.record(payload, cause)

        return _hook
