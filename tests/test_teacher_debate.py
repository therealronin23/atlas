"""
Tests para TeacherDebate — debate determinista entre propuestas LLM y priores verificados.

StubEmbedder es bag-of-words SHA-256: mismo vocabulario (distinto orden) → score ~1.0.
Vocabulario diferente → score bajo. Los tests usan solapamiento léxico real para
controlar el score sin red ni subprocesos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.immunity.lesson_recaller import LessonRecaller
from atlas.immunity.teacher_debate import (
    DebateOutcome,
    LessonProposal,
    TeacherDebate,
    _lesson_stance,
)
from atlas.memory.embeddings import StubEmbedder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS_EV = {"verdict": "pass"}


def _make_store(tmp_path: Path) -> LessonStore:
    return LessonStore(tmp_path / "lessons")


def _make_lesson(
    lid: str,
    avoid_pattern: str,
    detection_heuristic: str,
    stance: str = "avoid",
    title: str = "t",
) -> Lesson:
    return Lesson(
        id=lid,
        title=title,
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic=detection_heuristic,
        avoid_pattern=avoid_pattern,
        evidence=_PASS_EV,
        tags=(f"stance:{stance}",),
    )


def _make_debate(store: LessonStore) -> TeacherDebate:
    recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
    return TeacherDebate(store, recaller)


# ---------------------------------------------------------------------------
# _lesson_stance helper
# ---------------------------------------------------------------------------


class TestLessonStance:
    def test_reads_tag(self) -> None:
        lesson = _make_lesson("l1", "pat", "heuristic", stance="allow")
        assert _lesson_stance(lesson) == "allow"

    def test_defaults_to_avoid(self) -> None:
        # Lección sin tag de stance
        lesson = Lesson(
            id="l0",
            title="t",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h",
            avoid_pattern="p",
            evidence=_PASS_EV,
        )
        assert _lesson_stance(lesson) == "avoid"


# ---------------------------------------------------------------------------
# CORROBORATED
# ---------------------------------------------------------------------------


class TestCorroborated:
    def test_corroborated(self, tmp_path: Path) -> None:
        """Propuesta con alto solapamiento léxico y misma postura → CORROBORATED."""
        store = _make_store(tmp_path)
        # Lección existente con vocabulario específico
        store.add(_make_lesson("l-cor-01", "eval user_input shell", "detectar eval"))

        debate = _make_debate(store)
        proposal = LessonProposal(
            detection_heuristic="detectar eval",
            avoid_pattern="eval user_input shell",  # mismo vocabulario
            stance="avoid",
            rationale="igual que la lección existente",
            teacher_id="gpt-maestro",
        )
        result = debate.consider(proposal)

        assert result.outcome == DebateOutcome.CORROBORATED
        assert result.matched_lesson_id == "l-cor-01"
        assert result.score >= 0.8
        assert result.lesson_id is None  # no se crea lección nueva

    def test_no_duplicate_added(self, tmp_path: Path) -> None:
        """CORROBORATED no añade lecciones al store."""
        store = _make_store(tmp_path)
        store.add(_make_lesson("l-cor-02", "exec shell cmd", "detectar exec"))

        debate = _make_debate(store)
        before = len(store.all())

        proposal = LessonProposal(
            detection_heuristic="detectar exec",
            avoid_pattern="exec shell cmd",
            stance="avoid",
            rationale="repetida",
            teacher_id="t1",
        )
        result = debate.consider(proposal)
        assert result.outcome == DebateOutcome.CORROBORATED
        assert len(store.all()) == before


# ---------------------------------------------------------------------------
# CONTRADICTED
# ---------------------------------------------------------------------------


class TestContradicted:
    def test_contradicted_stance_mismatch(self, tmp_path: Path) -> None:
        """Alto solapamiento pero postura opuesta → CONTRADICTED, store no muta."""
        store = _make_store(tmp_path)
        store.add(_make_lesson("l-con-01", "sql injection query", "detectar sql"))

        debate = _make_debate(store)
        before = len(store.all())

        proposal = LessonProposal(
            detection_heuristic="detectar sql",
            avoid_pattern="sql injection query",  # mismo vocabulario
            stance="allow",  # opuesto al "avoid" del prior
            rationale="falso positivo según maestro",
            teacher_id="gpt-maestro",
        )
        result = debate.consider(proposal)

        assert result.outcome == DebateOutcome.CONTRADICTED
        assert result.matched_lesson_id == "l-con-01"
        assert result.score >= 0.8
        assert result.lesson_id is None
        assert len(store.all()) == before

    def test_contradicted_reason_mentions_prior(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.add(_make_lesson("l-con-02", "path traversal dotdot", "detectar path"))

        debate = _make_debate(store)
        proposal = LessonProposal(
            detection_heuristic="detectar path",
            avoid_pattern="path traversal dotdot",
            stance="allow",
            rationale="x",
            teacher_id="t1",
        )
        result = debate.consider(proposal)
        assert "l-con-02" in result.reason
        assert "prior" in result.reason.lower() or "verificad" in result.reason.lower()


# ---------------------------------------------------------------------------
# ACCEPTED_NEW
# ---------------------------------------------------------------------------


class TestAcceptedNew:
    def test_novel_avoid_accepted(self, tmp_path: Path) -> None:
        """Propuesta novel stance='avoid' → ACCEPTED_NEW, store crece en 1."""
        store = _make_store(tmp_path)
        before = len(store.all())

        debate = _make_debate(store)
        proposal = LessonProposal(
            detection_heuristic="xyzabc123 nuevo patron completamente diferente",
            avoid_pattern="xyzabc123 patron muy raro nunca visto antes",
            stance="avoid",
            rationale="descubierto en audit",
            teacher_id="gemini-pro",
        )
        result = debate.consider(proposal)

        assert result.outcome == DebateOutcome.ACCEPTED_NEW
        assert result.lesson_id is not None
        assert len(store.all()) == before + 1

    def test_accepted_lesson_has_correct_tags_and_evidence(self, tmp_path: Path) -> None:
        """La lección aceptada tiene tags stance/teacher y evidence verdict=pass."""
        store = _make_store(tmp_path)
        debate = _make_debate(store)

        proposal = LessonProposal(
            detection_heuristic="zzz111 rare unique pattern foobar",
            avoid_pattern="zzz111 rare foobar unique",
            stance="avoid",
            rationale="teacher rationale text",
            teacher_id="claude-teacher",
        )
        result = debate.consider(proposal)
        assert result.outcome == DebateOutcome.ACCEPTED_NEW

        lesson = store.get(result.lesson_id)  # type: ignore[arg-type]
        assert lesson is not None
        assert "stance:avoid" in lesson.tags
        assert "teacher:claude-teacher" in lesson.tags
        assert lesson.evidence["verdict"] == "pass"
        assert lesson.evidence["teacher_id"] == "claude-teacher"
        assert lesson.evidence["stance"] == "avoid"
        assert lesson.provenance == LessonProvenance.EXTERNAL_SOURCE

    def test_accepted_lesson_recalled_afterwards(self, tmp_path: Path) -> None:
        """Tras ACCEPTED_NEW, recall con mismo texto la encuentra."""
        store = _make_store(tmp_path)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        debate = TeacherDebate(store, recaller)

        proposal = LessonProposal(
            detection_heuristic="qqqxxx unique recall test heuristic",
            avoid_pattern="qqqxxx unique recall test pattern",
            stance="avoid",
            rationale="test",
            teacher_id="t1",
        )
        result = debate.consider(proposal)
        assert result.outcome == DebateOutcome.ACCEPTED_NEW

        recaller.index()
        recall = recaller.recall("qqqxxx unique recall test pattern qqqxxx unique recall test heuristic")
        assert recall is not None
        assert recall.matched


# ---------------------------------------------------------------------------
# REJECTED
# ---------------------------------------------------------------------------


class TestRejected:
    def test_novel_allow_rejected_by_default_verifier(self, tmp_path: Path) -> None:
        """Propuesta novel stance='allow' → REJECTED por verifier conservador."""
        store = _make_store(tmp_path)
        before = len(store.all())

        debate = _make_debate(store)
        proposal = LessonProposal(
            detection_heuristic="mmm999 novel allow unique pattern",
            avoid_pattern="mmm999 novel allow unique",
            stance="allow",
            rationale="el maestro dice que es seguro",
            teacher_id="gpt4",
        )
        result = debate.consider(proposal)

        assert result.outcome == DebateOutcome.REJECTED
        assert result.lesson_id is None
        assert len(store.all()) == before

    def test_injected_verifier_false_always_rejected(self, tmp_path: Path) -> None:
        """Verifier inyectado que siempre devuelve False → REJECTED."""
        store = _make_store(tmp_path)
        recaller = LessonRecaller(store, embedder=StubEmbedder(dim=64), threshold=0.8)
        debate = TeacherDebate(store, recaller, verifier=lambda _p: False)

        proposal = LessonProposal(
            detection_heuristic="bbb777 verifier override test",
            avoid_pattern="bbb777 verifier override",
            stance="avoid",
            rationale="deberia pasar el default pero no el inyectado",
            teacher_id="t1",
        )
        result = debate.consider(proposal)
        assert result.outcome == DebateOutcome.REJECTED
        assert len(store.all()) == 0


# ---------------------------------------------------------------------------
# debate_batch — estado evoluciona entre propuestas
# ---------------------------------------------------------------------------


class TestDebateBatch:
    def test_state_evolves_novel_then_corroborated(self, tmp_path: Path) -> None:
        """Primera propuesta: ACCEPTED_NEW. Segunda con mismo vocabulario: CORROBORATED."""
        store = _make_store(tmp_path)
        debate = _make_debate(store)

        p1 = LessonProposal(
            detection_heuristic="lll444 batch test detection unique",
            avoid_pattern="lll444 batch test pattern unique",
            stance="avoid",
            rationale="primera",
            teacher_id="t1",
        )
        # Reformulación léxica: mismo vocabulario, distinto orden
        p2 = LessonProposal(
            detection_heuristic="unique lll444 detection test batch",
            avoid_pattern="unique lll444 pattern test batch",
            stance="avoid",
            rationale="reformulacion",
            teacher_id="t2",
        )

        results = debate.debate_batch([p1, p2])

        assert results[0].outcome == DebateOutcome.ACCEPTED_NEW
        assert results[1].outcome == DebateOutcome.CORROBORATED
        # La segunda reconoce la lección recién añadida
        assert results[1].matched_lesson_id == results[0].lesson_id

    def test_batch_length_matches_proposals(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        debate = _make_debate(store)

        proposals = [
            LessonProposal(
                detection_heuristic=f"det{i} aaa unique test",
                avoid_pattern=f"pat{i} aaa unique test",
                stance="avoid",
                rationale="r",
                teacher_id="t1",
            )
            for i in range(4)
        ]
        results = debate.debate_batch(proposals)
        assert len(results) == 4


# ---------------------------------------------------------------------------
# Provenance correcta en la lección aceptada
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_teacher_id_in_evidence_and_tags(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        debate = _make_debate(store)

        proposal = LessonProposal(
            detection_heuristic="ppp555 provenance test unique pattern",
            avoid_pattern="ppp555 provenance unique pattern test",
            stance="avoid",
            rationale="rationale text here",
            teacher_id="nemotron-v1",
        )
        result = debate.consider(proposal)
        assert result.outcome == DebateOutcome.ACCEPTED_NEW

        lesson = store.get(result.lesson_id)  # type: ignore[arg-type]
        assert lesson is not None
        assert lesson.evidence["teacher_id"] == "nemotron-v1"
        assert any("teacher:nemotron-v1" == t for t in lesson.tags)

    def test_provenance_is_external_source(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        debate = _make_debate(store)

        proposal = LessonProposal(
            detection_heuristic="rrr888 external provenance unique",
            avoid_pattern="rrr888 external unique provenance",
            stance="avoid",
            rationale="r",
            teacher_id="t1",
        )
        result = debate.consider(proposal)
        lesson = store.get(result.lesson_id)  # type: ignore[arg-type]
        assert lesson is not None
        assert lesson.provenance == LessonProvenance.EXTERNAL_SOURCE


# ---------------------------------------------------------------------------
# Determinismo con StubEmbedder
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_outcome(self, tmp_path: Path) -> None:
        """Dos debates independientes con el mismo input producen el mismo outcome."""
        def run(base: Path) -> DebateOutcome:
            s = _make_store(base)
            s.add(_make_lesson("l-det", "aaa bbb ccc ddd", "detectar aaa"))
            d = _make_debate(s)
            p = LessonProposal(
                detection_heuristic="detectar aaa",
                avoid_pattern="aaa bbb ccc ddd",
                stance="avoid",
                rationale="r",
                teacher_id="t1",
            )
            return d.consider(p).outcome

        r1 = run(tmp_path / "run1")
        r2 = run(tmp_path / "run2")
        assert r1 == r2 == DebateOutcome.CORROBORATED
