"""
Capa 2 — Cascada con routing. Fakes para producers y hub: sin red,
sin subprocesos, sin GUI. El verificador de capa 1 es el real, con
verificadores fake dentro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    UniversalVerifier,
    Verdict,
)
from atlas.router.cascade import (
    CascadeRouter,
    CostLedger,
    Difficulty,
    InferenceProducer,
    RuleBasedDifficultyEstimator,
    TaskSpec,
)


@dataclass
class FakeProducer:
    producer_id: str
    cost: CostTier
    capability: Difficulty
    code: str = "x = 1"
    produced: list[TaskSpec] = field(default_factory=list)

    def produce(self, spec: TaskSpec) -> Artifact:
        self.produced.append(spec)
        return Artifact(
            kind=spec.kind,
            payload={"code": self.code},
            producer_cost=self.cost,
        )


@dataclass
class FakeChainVerifier:
    """Verificador de capa 1 con veredicto programable por código producido."""

    verifier_id: str
    cost: CostTier
    passing_codes: set[str] = field(default_factory=set)

    def applies_to(self, artifact: Artifact) -> bool:
        return "code" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        ok = artifact.payload["code"] in self.passing_codes
        return Evidence(
            verdict=Verdict.PASS if ok else Verdict.FAIL,
            checks=(Check(name=self.verifier_id, passed=ok, cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="" if ok else "código no esperado",
        )


def _spec(intent: str = "implementa la función", kind: ArtifactKind = ArtifactKind.CODE) -> TaskSpec:
    return TaskSpec(intent=intent, kind=kind)


class TestRuleBasedDifficultyEstimator:
    @pytest.mark.parametrize(
        "intent,expected",
        [
            ("renombra la variable foo a bar", Difficulty.MECHANICAL),
            ("corrige el typo del docstring", Difficulty.MECHANICAL),
            ("implementa la función de parseo", Difficulty.STANDARD),
            ("diseña la arquitectura del enjambre", Difficulty.HARD),
            ("evalúa el trade-off de seguridad", Difficulty.HARD),
        ],
    )
    def test_estimates(self, intent: str, expected: Difficulty) -> None:
        assert RuleBasedDifficultyEstimator().estimate(_spec(intent)) is expected

    def test_hard_wins_over_mechanical_on_mixed_signals(self) -> None:
        # "renombra" (MECHANICAL) + "seguridad" (HARD) → HARD: mejor pagar
        # de más que verificar de menos.
        spec = _spec("renombra el módulo de seguridad")
        assert RuleBasedDifficultyEstimator().estimate(spec) is Difficulty.HARD


class TestCascadeRouting:
    def _verifier(self, passing: set[str]) -> UniversalVerifier:
        return UniversalVerifier(
            [FakeChainVerifier("chk", CostTier.STATIC, passing_codes=passing)]
        )

    def test_cheapest_capable_producer_wins(self) -> None:
        cheap = FakeProducer("local", CostTier.MODEL, Difficulty.STANDARD, code="ok")
        frontier = FakeProducer("frontier", CostTier.FRONTIER, Difficulty.HARD, code="ok")
        router = CascadeRouter(self._verifier({"ok"}), [frontier, cheap])
        result = router.route(_spec("implementa la función"))
        assert result.verified
        assert result.attempts[0].producer_id == "local"
        assert frontier.produced == []
        assert result.escalations == 0

    def test_escalates_on_fail(self) -> None:
        cheap = FakeProducer("local", CostTier.MODEL, Difficulty.STANDARD, code="malo")
        frontier = FakeProducer("frontier", CostTier.FRONTIER, Difficulty.HARD, code="ok")
        router = CascadeRouter(self._verifier({"ok"}), [cheap, frontier])
        result = router.route(_spec())
        assert result.verified
        assert result.escalations == 1
        assert [a.producer_id for a in result.attempts] == ["local", "frontier"]
        assert result.attempts[0].verdict is Verdict.FAIL

    def test_escalation_enables_verifier_via_asymmetric_rule(self) -> None:
        # Verificador cuesta MODEL: no puede verificar a un producer MODEL
        # (no es más barato) → UNKNOWN → escala a FRONTIER, donde sí aplica.
        verifier = UniversalVerifier(
            [FakeChainVerifier("caro", CostTier.MODEL, passing_codes={"ok"})]
        )
        cheap = FakeProducer("local", CostTier.MODEL, Difficulty.STANDARD, code="ok")
        frontier = FakeProducer("frontier", CostTier.FRONTIER, Difficulty.HARD, code="ok")
        router = CascadeRouter(verifier, [cheap, frontier])
        result = router.route(_spec())
        assert result.attempts[0].verdict is Verdict.UNKNOWN
        assert result.attempts[1].verdict is Verdict.PASS
        assert result.verified

    def test_exhaustion_returns_honest_verdict(self) -> None:
        producers = [
            FakeProducer("a", CostTier.MODEL, Difficulty.HARD, code="malo"),
            FakeProducer("b", CostTier.FRONTIER, Difficulty.HARD, code="peor"),
        ]
        router = CascadeRouter(self._verifier({"ok"}), producers)  # nada pasa
        result = router.route(_spec())
        assert not result.verified
        assert result.evidence.verdict is Verdict.FAIL
        assert len(result.attempts) == 2

    def test_capability_filter(self) -> None:
        weak = FakeProducer("débil", CostTier.MODEL, Difficulty.MECHANICAL, code="ok")
        strong = FakeProducer("fuerte", CostTier.FRONTIER, Difficulty.HARD, code="ok")
        router = CascadeRouter(self._verifier({"ok"}), [weak, strong])
        result = router.route(_spec("diseña la arquitectura"))
        assert weak.produced == []
        assert result.attempts[0].producer_id == "fuerte"

    def test_no_capable_producer_is_unknown(self) -> None:
        weak = FakeProducer("débil", CostTier.MODEL, Difficulty.MECHANICAL)
        router = CascadeRouter(self._verifier({"ok"}), [weak])
        result = router.route(_spec("diseña la arquitectura"))
        assert result.evidence.verdict is Verdict.UNKNOWN
        assert result.artifact is None
        assert "capability" in result.evidence.reason

    def test_governance_blocked_never_enters(self) -> None:
        router = CascadeRouter(self._verifier({"ok"}), [])
        spec = TaskSpec(
            intent="haz algo", kind=ArtifactKind.CODE, metadata={"governance_blocked": True}
        )
        with pytest.raises(ValueError, match="governance"):
            router.route(spec)

    def test_understated_producer_cost_is_corrected(self) -> None:
        # Un producer que declara su artifact más barato de lo que es
        # burlaría la regla asimétrica; el router lo corrige.
        @dataclass
        class LyingProducer(FakeProducer):
            def produce(self, spec: TaskSpec) -> Artifact:
                return Artifact(
                    kind=spec.kind, payload={"code": "ok"}, producer_cost=CostTier.FREE
                )

        liar = LyingProducer("mentiroso", CostTier.FRONTIER, Difficulty.HARD)
        router = CascadeRouter(self._verifier({"ok"}), [liar])
        result = router.route(_spec())
        assert result.artifact is not None
        assert result.artifact.producer_cost is CostTier.FRONTIER

    def test_result_to_dict_serializable(self) -> None:
        import json

        router = CascadeRouter(
            self._verifier({"ok"}),
            [FakeProducer("p", CostTier.MODEL, Difficulty.STANDARD, code="ok")],
        )
        json.dumps(router.route(_spec()).to_dict())


class TestCostLedger:
    def test_cost_per_verified_result(self) -> None:
        ledger = CostLedger()
        verifier = UniversalVerifier(
            [FakeChainVerifier("chk", CostTier.STATIC, passing_codes={"ok"})]
        )
        producers = [
            FakeProducer("local", CostTier.MODEL, Difficulty.STANDARD, code="malo"),
            FakeProducer("frontier", CostTier.FRONTIER, Difficulty.HARD, code="ok"),
        ]
        router = CascadeRouter(verifier, producers, ledger=ledger)
        router.route(_spec())
        # intento 1: MODEL(5)+STATIC(1)=6; intento 2: FRONTIER(6)+STATIC(1)=7
        assert ledger.spent_units == 13
        assert ledger.verified_count == 1
        assert ledger.attempt_count == 2
        assert ledger.cost_per_verified_result() == 13.0

    def test_no_verified_results_is_none(self) -> None:
        assert CostLedger().cost_per_verified_result() is None

    def test_ledger_accumulates_across_tasks(self) -> None:
        ledger = CostLedger()
        verifier = UniversalVerifier(
            [FakeChainVerifier("chk", CostTier.STATIC, passing_codes={"ok"})]
        )
        router = CascadeRouter(
            verifier,
            [FakeProducer("p", CostTier.MODEL, Difficulty.STANDARD, code="ok")],
            ledger=ledger,
        )
        router.route(_spec("tarea 1"))
        router.route(_spec("tarea 2"))
        assert ledger.verified_count == 2
        assert ledger.cost_per_verified_result() == 6.0


@dataclass
class FakeInferenceResponse:
    text: str = "print('hola')"
    provider: str = "fake"
    model: str = "fake-1"
    latency_ms: int = 10
    success: bool = True
    mode: str = "stub"


class FakeHub:
    def __init__(self, response: FakeInferenceResponse) -> None:
        self._response = response
        self.requests: list[Any] = []

    def infer(self, request: Any) -> FakeInferenceResponse:
        self.requests.append(request)
        return self._response


class TestInferenceProducer:
    def test_l1_maps_to_model_cost(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        producer = InferenceProducer(
            FakeHub(FakeInferenceResponse()),
            level=InferenceLevel.L1,
            capability=Difficulty.STANDARD,
        )
        assert producer.cost is CostTier.MODEL
        assert producer.producer_id == "inference:L1"

    def test_l2_maps_to_frontier_cost(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        producer = InferenceProducer(
            FakeHub(FakeInferenceResponse()),
            level=InferenceLevel.L2,
            capability=Difficulty.HARD,
        )
        assert producer.cost is CostTier.FRONTIER

    def test_produce_builds_code_artifact(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        hub = FakeHub(FakeInferenceResponse(text="x = 2"))
        producer = InferenceProducer(hub, level=InferenceLevel.L1, capability=Difficulty.STANDARD)
        artifact = producer.produce(_spec("implementa", kind=ArtifactKind.CODE))
        assert artifact.payload["code"] == "x = 2"
        assert artifact.producer_cost is CostTier.MODEL
        assert artifact.metadata["provider"] == "fake"
        assert hub.requests[0].level is InferenceLevel.L1

    def test_produce_patch_uses_diff_key(self) -> None:
        from atlas.core.inference_hub import InferenceLevel

        producer = InferenceProducer(
            FakeHub(FakeInferenceResponse(text="--- a\n+++ b")),
            level=InferenceLevel.L2,
            capability=Difficulty.HARD,
        )
        artifact = producer.produce(_spec("parchea", kind=ArtifactKind.PATCH))
        assert artifact.payload["diff"].startswith("---")
        assert "code" not in artifact.payload
