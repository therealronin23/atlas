"""
ADR-048 — VerifiedProducer (lazo cerrado). Productores, verificador, panel,
grounding y aprendizaje fake: sin LLM, sin git, sin red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.core.adversarial_panel import AdversarialPanel, Objection, Severity
from atlas.core.verified_producer import VerifiedProducer
from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    UniversalVerifier,
    Verdict,
)
from atlas.router.cascade import Difficulty, TaskSpec


@dataclass
class FakeProducer:
    producer_id: str
    cost: CostTier
    capability: Difficulty
    diff: str
    seen_contexts: list[str] = field(default_factory=list)

    def produce(self, spec: TaskSpec) -> Artifact:
        self.seen_contexts.append(str(spec.metadata.get("context", "")))
        return Artifact(
            kind=ArtifactKind.PATCH, payload={"diff": self.diff}, producer_cost=self.cost
        )


@dataclass
class KeyedVerifier:
    """Verificador capa-1 fake: PASS si el diff está en passing. Cost FREE para
    ser más barato que cualquier productor (regla asimétrica)."""
    verifier_id: str = "chk"
    cost: CostTier = CostTier.FREE
    passing: frozenset[str] = frozenset()

    def applies_to(self, artifact: Artifact) -> bool:
        return "diff" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        ok = artifact.payload["diff"] in self.passing
        return Evidence(
            verdict=Verdict.PASS if ok else Verdict.FAIL,
            checks=(Check(name="chk", passed=ok, cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=("chk",),
            reason="" if ok else f"diff no esperado: {artifact.payload['diff'][:20]}",
        )


@dataclass
class FakeEstimator:
    value: Difficulty

    def estimate(self, spec: TaskSpec) -> Difficulty:
        return self.value


@dataclass
class FakeGrounding:
    text: str = "evita el doble escritor Merkle"
    ids: tuple[str, ...] = ("lesson-1",)

    def context_for(self, spec: TaskSpec) -> tuple[str, tuple[str, ...]]:
        return self.text, self.ids


@dataclass
class RecordingLearning:
    cycles: list[dict[str, Any]] = field(default_factory=list)

    def record_cycle(self, spec, *, failures, success) -> None:  # noqa: ANN001
        self.cycles.append({"failures": failures, "success": success})


@dataclass
class FakeReviewer:
    reviewer_id: str
    provider: str
    severity: Severity = Severity.NONE
    detail: str = ""

    def review(self, diff: str, context: str = "") -> Objection:
        return Objection(self.reviewer_id, self.provider, self.severity, self.detail)


def _verifier(*passing: str) -> UniversalVerifier:
    return UniversalVerifier([KeyedVerifier(passing=frozenset(passing))])


def _spec(intent: str = "arregla algo", **meta) -> TaskSpec:
    return TaskSpec(intent=intent, kind=ArtifactKind.PATCH, metadata=meta)


class TestLoopCore:
    def test_cheapest_capable_producer_verified(self) -> None:
        cheap = FakeProducer("det", CostTier.STATIC, Difficulty.STANDARD, diff="ok")
        llm = FakeProducer("llm", CostTier.MODEL, Difficulty.HARD, diff="ok")
        vp = VerifiedProducer([llm, cheap], _verifier("ok"),
                              estimator=FakeEstimator(Difficulty.STANDARD))
        out = vp.produce(_spec())
        assert out.verified
        assert out.attempts[0].producer_id == "det"
        assert llm.seen_contexts == []  # no escaló

    def test_reflexion_feeds_failure_into_next_producer(self) -> None:
        det = FakeProducer("det", CostTier.STATIC, Difficulty.HARD, diff="malo")
        llm = FakeProducer("llm", CostTier.MODEL, Difficulty.HARD, diff="ok")
        vp = VerifiedProducer([det, llm], _verifier("ok"),
                              estimator=FakeEstimator(Difficulty.HARD))
        out = vp.produce(_spec())
        assert out.verified
        # el LLM vio el contexto con el fallo del determinista
        assert "Intentos previos fallaron" in llm.seen_contexts[0]
        assert "det" in llm.seen_contexts[0]

    def test_exhaustion_returns_honest_fail(self) -> None:
        vp = VerifiedProducer(
            [FakeProducer("a", CostTier.STATIC, Difficulty.HARD, diff="x"),
             FakeProducer("b", CostTier.MODEL, Difficulty.HARD, diff="y")],
            _verifier("ok"),  # nada pasa
            estimator=FakeEstimator(Difficulty.HARD),
        )
        out = vp.produce(_spec())
        assert not out.verified
        assert out.evidence.verdict is Verdict.FAIL
        assert len(out.attempts) == 2

    def test_budget_caps_the_loop(self) -> None:
        producers = [
            FakeProducer("a", CostTier.MODEL, Difficulty.HARD, diff="malo"),
            FakeProducer("b", CostTier.FRONTIER, Difficulty.HARD, diff="ok"),
        ]
        # presupuesto solo alcanza el primer intento (MODEL=5 + FREE=0 = 5)
        vp = VerifiedProducer(producers, _verifier("ok"),
                              estimator=FakeEstimator(Difficulty.HARD), budget_units=5)
        out = vp.produce(_spec())
        assert not out.verified
        assert len(out.attempts) == 1  # el segundo no llegó a correr
        assert producers[1].seen_contexts == []


class TestGrounding:
    def test_grounding_context_reaches_producer(self) -> None:
        prod = FakeProducer("det", CostTier.STATIC, Difficulty.STANDARD, diff="ok")
        vp = VerifiedProducer([prod], _verifier("ok"),
                              grounding=FakeGrounding(),
                              estimator=FakeEstimator(Difficulty.STANDARD))
        out = vp.produce(_spec())
        assert "doble escritor Merkle" in prod.seen_contexts[0]
        assert out.grounded_with == ("lesson-1",)


class TestPanel:
    def _panel(self, *reviewers) -> AdversarialPanel:
        return AdversarialPanel(list(reviewers))

    def test_panel_runs_when_gated_and_can_block(self) -> None:
        prod = FakeProducer("llm", CostTier.MODEL, Difficulty.HARD, diff="ok")
        panel = self._panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer("b", "gemini", Severity.MAJOR, "rompe el caso vacío"),
        )
        # HARD → should_convene True; capa1 pasa pero el panel bloquea
        vp = VerifiedProducer([prod], _verifier("ok"), panel=panel,
                              estimator=FakeEstimator(Difficulty.HARD))
        out = vp.produce(_spec())
        assert not out.verified
        assert out.attempts[-1].stage == "panel"
        assert "caso vacío" in out.evidence.reason

    def test_panel_skipped_for_trivial(self) -> None:
        # MECHANICAL + low risk → gating salta el panel aunque haya objeción.
        prod = FakeProducer("det", CostTier.STATIC, Difficulty.MECHANICAL, diff="ok")
        panel = self._panel(
            FakeReviewer("a", "groq", Severity.BLOCKING, "no debería verse"),
            FakeReviewer("b", "gemini", Severity.NONE),
        )
        vp = VerifiedProducer([prod], _verifier("ok"), panel=panel,
                              estimator=FakeEstimator(Difficulty.MECHANICAL))
        out = vp.produce(_spec(risk="low"))
        assert out.verified  # el panel no se convocó
        assert out.attempts[-1].stage == "verify"

    def test_panel_pass_lets_through(self) -> None:
        prod = FakeProducer("llm", CostTier.MODEL, Difficulty.HARD, diff="ok")
        panel = self._panel(FakeReviewer("a", "groq"), FakeReviewer("b", "gemini"))
        vp = VerifiedProducer([prod], _verifier("ok"), panel=panel,
                              estimator=FakeEstimator(Difficulty.HARD))
        assert vp.produce(_spec()).verified


class TestLearning:
    def test_records_success_with_prior_failures(self) -> None:
        learning = RecordingLearning()
        vp = VerifiedProducer(
            [FakeProducer("det", CostTier.STATIC, Difficulty.HARD, diff="malo"),
             FakeProducer("llm", CostTier.MODEL, Difficulty.HARD, diff="ok")],
            _verifier("ok"), learning=learning,
            estimator=FakeEstimator(Difficulty.HARD),
        )
        vp.produce(_spec())
        assert len(learning.cycles) == 1
        assert learning.cycles[0]["success"] is True
        assert len(learning.cycles[0]["failures"]) == 1  # el det falló antes

    def test_records_failure_on_exhaustion(self) -> None:
        learning = RecordingLearning()
        vp = VerifiedProducer(
            [FakeProducer("a", CostTier.STATIC, Difficulty.HARD, diff="x")],
            _verifier("ok"), learning=learning,
            estimator=FakeEstimator(Difficulty.HARD),
        )
        vp.produce(_spec())
        assert learning.cycles[0]["success"] is False


def test_outcome_serializable() -> None:
    import json

    vp = VerifiedProducer(
        [FakeProducer("det", CostTier.STATIC, Difficulty.STANDARD, diff="ok")],
        _verifier("ok"), estimator=FakeEstimator(Difficulty.STANDARD),
    )
    json.dumps(vp.produce(_spec()).to_dict())
