"""
ADR-048 fase D — LLMProducer (potenciador). Restricciones de lección + allowed_paths.
Productor interno fake, sin red.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atlas.core.llm_producer import LLMProducer
from atlas.core.verify import Artifact, ArtifactKind, CostTier
from atlas.router.cascade import Difficulty, TaskSpec


@dataclass
class FakeInner:
    producer_id: str = "inference:l1"
    cost: CostTier = CostTier.MODEL
    capability: Difficulty = Difficulty.STANDARD
    seen: list[str] = field(default_factory=list)
    stamp_paths: bool = False

    def produce(self, spec: TaskSpec) -> Artifact:
        self.seen.append(str(spec.metadata.get("context", "")))
        meta = {"provider": "groq"}
        if self.stamp_paths:
            meta["allowed_paths"] = ["already/set.py"]
        return Artifact(
            kind=ArtifactKind.PATCH,
            payload={"diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"},
            producer_cost=self.cost,
            metadata=meta,
        )


def _spec(**meta) -> TaskSpec:
    return TaskSpec(intent="haz algo", kind=ArtifactKind.PATCH, metadata=meta)


class TestConstraints:
    def test_avoid_patterns_injected_as_prohibitions(self) -> None:
        inner = FakeInner()
        p = LLMProducer(inner, avoid_patterns=("uses double Merkle writer",))
        p.produce(_spec())
        assert "NO uses double Merkle writer" in inner.seen[0]
        assert "Restricciones aprendidas" in inner.seen[0]

    def test_constraints_append_to_existing_context(self) -> None:
        inner = FakeInner()
        p = LLMProducer(inner, avoid_patterns=("X",))
        p.produce(_spec(context="contexto previo"))
        assert "contexto previo" in inner.seen[0]
        assert "NO X" in inner.seen[0]

    def test_no_patterns_leaves_context_untouched(self) -> None:
        inner = FakeInner()
        LLMProducer(inner).produce(_spec(context="solo esto"))
        assert inner.seen[0] == "solo esto"


class TestAllowedPaths:
    def test_stamps_allowed_paths_from_task(self) -> None:
        inner = FakeInner()
        out = LLMProducer(inner).produce(_spec(allowed_paths=["pkg/y.py"]))
        assert out.metadata["allowed_paths"] == ["pkg/y.py"]

    def test_does_not_override_inner_paths(self) -> None:
        inner = FakeInner(stamp_paths=True)
        out = LLMProducer(inner).produce(_spec(allowed_paths=["task/path.py"]))
        assert out.metadata["allowed_paths"] == ["already/set.py"]


def test_producer_protocol_delegates() -> None:
    inner = FakeInner()
    p = LLMProducer(inner)
    assert p.producer_id == "llm:inference:l1"
    assert p.cost is CostTier.MODEL
    assert p.capability is Difficulty.STANDARD
