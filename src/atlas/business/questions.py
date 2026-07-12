"""AdaptiveQuestionEngine — el lazo obligatorio: Atlas pregunta concreto →
usuario responde → Atlas interpreta y lo MUESTRA → usuario confirma/corrige
→ Atlas sigue. Nunca se avanza sobre una interpretación sin confirmar."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.business.models import (
    AdaptiveQuestion,
    Answer,
    OnboardingSession,
    Proposed,
    QuestionPack,
    SessionStatus,
)


class OnboardingError(ValueError):
    """Transición o respuesta inválida en una sesión de onboarding."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_pack(path: Path) -> QuestionPack:
    return QuestionPack.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_all_packs(packs_dir: Path) -> dict[str, QuestionPack]:
    packs: dict[str, QuestionPack] = {}
    if packs_dir.exists():
        for file in sorted(packs_dir.glob("*.json")):
            pack = load_pack(file)
            packs[pack.pack_id] = pack
    return packs


def _question_by_id(pack: QuestionPack, question_id: str) -> AdaptiveQuestion:
    for q in pack.questions:
        if q.question_id == question_id:
            return q
    raise OnboardingError(f"pregunta desconocida en el pack: {question_id}")


def _option_label(question: AdaptiveQuestion, option_id: str) -> str:
    for opt in question.options:
        if opt.option_id == option_id:
            return opt.label
    raise OnboardingError(
        f"{option_id!r} no es una opción válida de {question.question_id}"
    )


def _validate_and_interpret(
    question: AdaptiveQuestion, value: Any, uncertain: bool,
) -> str:
    if uncertain:
        if not question.uncertainty_allowed:
            raise OnboardingError(
                f"{question.question_id} no admite 'no sé' — respuesta obligatoria"
            )
        return "El usuario no lo sabe todavía; Atlas continuará sin este dato."

    if question.input_type.value == "single_choice":
        if not isinstance(value, str):
            raise OnboardingError(f"{question.question_id} espera una opción única")
        return _option_label(question, value)

    if question.input_type.value == "multi_choice":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise OnboardingError(f"{question.question_id} espera una lista de opciones")
        v = question.validation
        if v.min_selected is not None and len(value) < v.min_selected:
            raise OnboardingError(
                f"{question.question_id} exige al menos {v.min_selected} opciones"
            )
        if v.max_selected is not None and len(value) > v.max_selected:
            raise OnboardingError(
                f"{question.question_id} admite como máximo {v.max_selected} opciones"
            )
        labels = [_option_label(question, v_) for v_ in value]
        return ", ".join(labels)

    if question.input_type.value == "number":
        if not isinstance(value, (int, float)):
            raise OnboardingError(f"{question.question_id} espera un número")
        v = question.validation
        if v.min is not None and value < v.min:
            raise OnboardingError(f"{question.question_id}: por debajo del mínimo")
        if v.max is not None and value > v.max:
            raise OnboardingError(f"{question.question_id}: por encima del máximo")
        return str(value)

    if question.input_type.value in {"text", "file_ref"}:
        if not isinstance(value, str) or not value.strip():
            raise OnboardingError(f"{question.question_id} espera texto no vacío")
        return value

    raise OnboardingError(f"input_type no soportado: {question.input_type}")


def _selected_option_ids(value: Any, uncertain: bool) -> list[str]:
    if uncertain:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return list(value)
    return []


class QuestionEngine:
    def start_session(
        self, pack: QuestionPack, *, demo: bool = False,
    ) -> OnboardingSession:
        return OnboardingSession(
            session_id=f"obs_{uuid.uuid4().hex[:10]}",
            sector_id=pack.sector_id,
            pack_id=pack.pack_id,
            status=SessionStatus.ACTIVE,
            answers=[],
            pending_questions=[q.question_id for q in pack.questions],
            created_at=_now(),
            updated_at=_now(),
            demo=demo,
        )

    def submit_answer(
        self,
        session: OnboardingSession,
        pack: QuestionPack,
        question_id: str,
        value: Any,
        *,
        uncertain: bool = False,
    ) -> OnboardingSession:
        if session.status is not SessionStatus.ACTIVE:
            raise OnboardingError(
                f"la sesión {session.session_id} no está activa "
                f"(status={session.status.value})"
            )
        if question_id not in session.pending_questions:
            raise OnboardingError(
                f"{question_id} no está pendiente en esta sesión"
            )
        question = _question_by_id(pack, question_id)
        interpreted = _validate_and_interpret(question, value, uncertain)

        answers = [*session.answers, Answer(
            question_id=question_id,
            value=value if not uncertain else None,
            uncertain=uncertain,
            interpreted=interpreted,
            confirmed=False,
        )]
        pending = [q for q in session.pending_questions if q != question_id]
        for rule in question.followup_rules:
            if rule.when_option in _selected_option_ids(value, uncertain) and (
                rule.ask not in pending
                and not any(a.question_id == rule.ask for a in answers)
            ):
                pending.append(rule.ask)

        return session.model_copy(update={
            "answers": answers, "pending_questions": pending,
            "updated_at": _now(),
        })

    def confirm_answer(
        self, session: OnboardingSession, question_id: str, *, corrected: bool = False,
    ) -> OnboardingSession:
        """El usuario confirma que Atlas entendió bien (o, si `corrected`,
        que ya corrigió). Sin esto, la respuesta queda sin confirmar y no
        cuenta para el resumen final."""
        answers = list(session.answers)
        for i in range(len(answers) - 1, -1, -1):
            if answers[i].question_id == question_id:
                answers[i] = answers[i].model_copy(update={"confirmed": True})
                return session.model_copy(update={
                    "answers": answers, "updated_at": _now(),
                })
        raise OnboardingError(f"sin respuesta previa para {question_id}")

    def skip_question(
        self, session: OnboardingSession, pack: QuestionPack, question_id: str,
    ) -> OnboardingSession:
        question = _question_by_id(pack, question_id)
        if not question.skip_allowed:
            raise OnboardingError(f"{question_id} no admite omitirse")
        if question_id not in session.pending_questions:
            raise OnboardingError(f"{question_id} no está pendiente en esta sesión")
        answers = [*session.answers, Answer(
            question_id=question_id, value=None, uncertain=True,
            interpreted="Omitida por el usuario.", confirmed=True,
        )]
        pending = [q for q in session.pending_questions if q != question_id]
        return session.model_copy(update={
            "answers": answers, "pending_questions": pending,
            "updated_at": _now(),
        })

    def build_preview(
        self, session: OnboardingSession, pack: QuestionPack,
    ) -> OnboardingSession:
        if session.pending_questions:
            raise OnboardingError(
                "quedan preguntas pendientes: "
                f"{session.pending_questions}"
            )
        unconfirmed = [a.question_id for a in session.answers if not a.confirmed]
        if unconfirmed:
            raise OnboardingError(
                f"respuestas sin confirmar: {unconfirmed}"
            )
        entities: set[str] = set()
        capabilities: set[str] = set()
        workbenches: set[str] = set()
        for answer in session.answers:
            if answer.uncertain:
                # "no sé" u omitida: no hay decisión, no se concede nada.
                continue
            question = _question_by_id(pack, answer.question_id)
            entities.update(question.resulting_entities)
            capabilities.update(question.resulting_capabilities)
            workbenches.update(question.resulting_workbenches)
        summary = "; ".join(
            f"{a.question_id} → {a.interpreted}" for a in session.answers
        )
        return session.model_copy(update={
            "status": SessionStatus.PREVIEW,
            "understanding_summary": summary,
            "proposed": Proposed(
                entities=sorted(entities), capabilities=sorted(capabilities),
                workbenches=sorted(workbenches), connector_pack=None,
            ),
            "updated_at": _now(),
        })

    def confirm_session(self, session: OnboardingSession) -> OnboardingSession:
        if session.status is not SessionStatus.PREVIEW:
            raise OnboardingError(
                f"la sesión debe estar en preview, está en {session.status.value}"
            )
        return session.model_copy(update={
            "status": SessionStatus.CONFIRMED, "updated_at": _now(),
        })

    def abandon_session(self, session: OnboardingSession) -> OnboardingSession:
        return session.model_copy(update={
            "status": SessionStatus.ABANDONED, "updated_at": _now(),
        })
