"""
Capa 1 — Verificador universal. Todo con fakes inyectados: sin red,
sin subprocesos reales, sin GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    OutputShapeVerifier,
    SandboxRunVerifier,
    StaticCodeVerifier,
    SuiteVerifier,
    UniversalVerifier,
    Verdict,
)


@dataclass
class FakeVerifier:
    verifier_id: str
    cost: CostTier
    verdict: Verdict = Verdict.PASS
    applies: bool = True
    calls: list[Artifact] = field(default_factory=list)
    reason: str = ""

    def applies_to(self, artifact: Artifact) -> bool:
        return self.applies

    def verify(self, artifact: Artifact) -> Evidence:
        self.calls.append(artifact)
        return Evidence(
            verdict=self.verdict,
            checks=(Check(name=self.verifier_id, passed=self.verdict is Verdict.PASS, cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason=self.reason,
        )


def _artifact(producer: CostTier = CostTier.MODEL) -> Artifact:
    return Artifact(kind=ArtifactKind.CODE, payload={"code": "x = 1"}, producer_cost=producer)


class TestUniversalVerifier:
    def test_runs_cheap_to_expensive(self) -> None:
        order: list[str] = []

        expensive = FakeVerifier("caro", CostTier.SUITE)
        cheap = FakeVerifier("barato", CostTier.STATIC)
        original_expensive, original_cheap = expensive.verify, cheap.verify
        expensive.verify = lambda a: (order.append("caro"), original_expensive(a))[1]  # type: ignore[method-assign]
        cheap.verify = lambda a: (order.append("barato"), original_cheap(a))[1]  # type: ignore[method-assign]

        uv = UniversalVerifier([expensive, cheap])
        evidence = uv.verify(_artifact())
        assert order == ["barato", "caro"]
        assert evidence.verdict is Verdict.PASS
        assert evidence.verifier_ids == ("barato", "caro")
        assert evidence.total_cost is CostTier.SUITE

    def test_short_circuits_on_fail(self) -> None:
        cheap = FakeVerifier("barato", CostTier.STATIC, verdict=Verdict.FAIL, reason="ast roto")
        expensive = FakeVerifier("caro", CostTier.SUITE)
        uv = UniversalVerifier([cheap, expensive])
        evidence = uv.verify(_artifact())
        assert evidence.verdict is Verdict.FAIL
        assert evidence.reason == "ast roto"
        assert expensive.calls == []

    def test_asymmetric_rule_returns_unknown(self) -> None:
        # Único verificador aplicable cuesta lo mismo que el productor → no
        # verifica nada: UNKNOWN explícito, nunca PASS fingido.
        same_cost = FakeVerifier("igual", CostTier.STATIC)
        uv = UniversalVerifier([same_cost])
        evidence = uv.verify(_artifact(producer=CostTier.STATIC))
        assert evidence.verdict is Verdict.UNKNOWN
        assert "asimétrica" in evidence.reason
        assert same_cost.calls == []

    def test_no_applicable_verifier_is_unknown(self) -> None:
        uv = UniversalVerifier([FakeVerifier("no-aplica", CostTier.FREE, applies=False)])
        assert uv.verify(_artifact()).verdict is Verdict.UNKNOWN

    def test_unknown_verifier_does_not_block(self) -> None:
        unsure = FakeVerifier("dudoso", CostTier.STATIC, verdict=Verdict.UNKNOWN, reason="sin datos")
        ok = FakeVerifier("ok", CostTier.SANDBOX)
        uv = UniversalVerifier([unsure, ok])
        evidence = uv.verify(_artifact())
        assert evidence.verdict is Verdict.PASS
        assert any("dudoso:unknown" == c.name for c in evidence.checks)

    def test_register(self) -> None:
        uv = UniversalVerifier()
        uv.register(FakeVerifier("v", CostTier.STATIC))
        assert uv.verify(_artifact()).verdict is Verdict.PASS


class TestEvidenceSerialization:
    def test_to_dict_round_trippable(self) -> None:
        evidence = Evidence(
            verdict=Verdict.PASS,
            checks=(Check(name="c1", passed=True, detail="d", cost=CostTier.STATIC),),
            total_cost=CostTier.STATIC,
            verifier_ids=("v1",),
        )
        d = evidence.to_dict()
        assert d["verdict"] == "pass"
        assert d["total_cost"] == "STATIC"
        assert d["checks"][0] == {"name": "c1", "passed": True, "detail": "d", "cost": "STATIC"}
        assert d["verifier_ids"] == ["v1"]
        assert d["created_at"]

        import json

        json.dumps(d)  # apto para Merkle/log


@dataclass
class FakeGuardResult:
    valid: bool
    violations: list[str] = field(default_factory=list)


class FakeGuard:
    def __init__(self, result: FakeGuardResult) -> None:
        self._result = result

    def validate(self, code: str) -> FakeGuardResult:
        return self._result


class TestStaticCodeVerifier:
    def test_pass(self) -> None:
        v = StaticCodeVerifier(FakeGuard(FakeGuardResult(valid=True)))
        assert v.applies_to(_artifact())
        assert v.verify(_artifact()).verdict is Verdict.PASS

    def test_fail_carries_violations(self) -> None:
        v = StaticCodeVerifier(FakeGuard(FakeGuardResult(valid=False, violations=["import os"])))
        evidence = v.verify(_artifact())
        assert evidence.verdict is Verdict.FAIL
        assert "import os" in evidence.reason

    def test_does_not_apply_to_claims(self) -> None:
        claim = Artifact(kind=ArtifactKind.CLAIM, payload={"text": "x"}, producer_cost=CostTier.MODEL)
        assert not StaticCodeVerifier(FakeGuard(FakeGuardResult(valid=True))).applies_to(claim)


@dataclass
class FakeValidationResult:
    valid: bool
    reasons: tuple[str, ...] = ()


class FakeAuditor:
    def __init__(self, result: FakeValidationResult) -> None:
        self._result = result

    def validate_output(self, snapshot: Any, output: Any) -> FakeValidationResult:
        return self._result


class TestOutputShapeVerifier:
    def _artifact(self) -> Artifact:
        return Artifact(
            kind=ArtifactKind.COMMAND_OUTPUT,
            payload={"snapshot": object(), "output": object()},
            producer_cost=CostTier.MODEL,
        )

    def test_pass(self) -> None:
        v = OutputShapeVerifier(FakeAuditor(FakeValidationResult(valid=True)))
        assert v.applies_to(self._artifact())
        assert v.verify(self._artifact()).verdict is Verdict.PASS

    def test_fail(self) -> None:
        v = OutputShapeVerifier(FakeAuditor(FakeValidationResult(valid=False, reasons=("shape mal",))))
        evidence = v.verify(self._artifact())
        assert evidence.verdict is Verdict.FAIL
        assert "shape mal" in evidence.reason

    def test_requires_snapshot_and_output(self) -> None:
        incomplete = Artifact(
            kind=ArtifactKind.COMMAND_OUTPUT, payload={"output": object()}, producer_cost=CostTier.MODEL
        )
        assert not OutputShapeVerifier(FakeAuditor(FakeValidationResult(valid=True))).applies_to(incomplete)


@dataclass
class FakeSandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class FakeSandbox:
    def __init__(self, result: FakeSandboxResult) -> None:
        self._result = result
        self.executed: list[str] = []

    def execute(self, code: str, **kwargs: Any) -> FakeSandboxResult:
        self.executed.append(code)
        return self._result


class TestSandboxRunVerifier:
    def test_pass(self) -> None:
        sandbox = FakeSandbox(FakeSandboxResult(success=True))
        v = SandboxRunVerifier(sandbox)
        assert v.verify(_artifact()).verdict is Verdict.PASS
        assert sandbox.executed == ["x = 1"]

    def test_fail_carries_stderr(self) -> None:
        v = SandboxRunVerifier(FakeSandbox(FakeSandboxResult(success=False, stderr="boom", exit_code=1)))
        evidence = v.verify(_artifact())
        assert evidence.verdict is Verdict.FAIL
        assert "boom" in evidence.reason


@dataclass
class FakeReport:
    passed: bool
    errors: list[str] = field(default_factory=list)


class FakeRunner:
    def __init__(self, report: FakeReport) -> None:
        self._report = report
        self.runs = 0

    def run(self) -> FakeReport:
        self.runs += 1
        return self._report


class TestSuiteVerifier:
    def _patch(self) -> Artifact:
        return Artifact(kind=ArtifactKind.PATCH, payload={"diff": "..."}, producer_cost=CostTier.MODEL)

    def test_pass(self) -> None:
        runner = FakeRunner(FakeReport(passed=True))
        v = SuiteVerifier(runner)
        assert v.applies_to(self._patch())
        assert v.verify(self._patch()).verdict is Verdict.PASS
        assert runner.runs == 1

    def test_fail(self) -> None:
        v = SuiteVerifier(FakeRunner(FakeReport(passed=False, errors=["pytest failed"])))
        evidence = v.verify(self._patch())
        assert evidence.verdict is Verdict.FAIL
        assert "pytest failed" in evidence.reason

    def test_only_applies_to_patches(self) -> None:
        assert not SuiteVerifier(FakeRunner(FakeReport(passed=True))).applies_to(_artifact())


class TestEndToEndCascade:
    """Cascada completa con los cuatro adaptadores y fakes."""

    def test_code_artifact_passes_static_then_sandbox(self) -> None:
        uv = UniversalVerifier(
            [
                SandboxRunVerifier(FakeSandbox(FakeSandboxResult(success=True))),
                StaticCodeVerifier(FakeGuard(FakeGuardResult(valid=True))),
            ]
        )
        evidence = uv.verify(_artifact(producer=CostTier.MODEL))
        assert evidence.verdict is Verdict.PASS
        assert evidence.verifier_ids == ("static_code", "sandbox_run")

    def test_static_fail_never_reaches_sandbox(self) -> None:
        sandbox = FakeSandbox(FakeSandboxResult(success=True))
        uv = UniversalVerifier(
            [
                SandboxRunVerifier(sandbox),
                StaticCodeVerifier(FakeGuard(FakeGuardResult(valid=False, violations=["eval"]))),
            ]
        )
        evidence = uv.verify(_artifact(producer=CostTier.MODEL))
        assert evidence.verdict is Verdict.FAIL
        assert sandbox.executed == []
