"""
Capa 1 — Verificador universal: seam único `verify(artifact) -> Evidence`.

Unifica los verificadores que ya existen (ASTGuard, ResultAuditor,
LayeredIsolationSandbox, ValidationRunner) detrás de una interfaz común,
sin tocarlos: cada uno entra por un adaptador.

Regla rectora (verificación asimétrica): ningún resultado sube por la
cascada sin un verificador MÁS BARATO que su productor. Si no existe,
el veredicto es UNKNOWN con razón explícita — nunca se finge verificación
(postmortem 2026-06-12: un sistema que miente sobre su readiness es más
débil que uno que dice "unknown").

Las capas 2 (routing) y 3 (enjambre) consumen `Evidence.to_dict()` tal
cual; este módulo no escribe Merkle ni expone CLI: quién llama al seam es
decisión de la capa 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Protocol


class ArtifactKind(str, Enum):
    CODE = "code"
    PATCH = "patch"
    COMMAND_OUTPUT = "command_output"
    CLAIM = "claim"
    METRIC_SAMPLE = "metric_sample"


class CostTier(IntEnum):
    """Coste ordinal: lo único que la regla asimétrica necesita es comparar."""

    FREE = 0
    STATIC = 1
    SHAPE = 2
    SANDBOX = 3
    SUITE = 4
    MODEL = 5      # modelos pequeños/gratis (L0/L1)
    FRONTIER = 6   # API frontier de pago (L2) — capa 2


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Artifact:
    kind: ArtifactKind
    payload: dict[str, Any]
    producer_cost: CostTier
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""
    cost: CostTier = CostTier.FREE

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "cost": self.cost.name,
        }


@dataclass(frozen=True)
class Evidence:
    verdict: Verdict
    checks: tuple[Check, ...] = ()
    total_cost: CostTier = CostTier.FREE
    verifier_ids: tuple[str, ...] = ()
    reason: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "checks": [c.to_dict() for c in self.checks],
            "total_cost": self.total_cost.name,
            "verifier_ids": list(self.verifier_ids),
            "reason": self.reason,
            "created_at": self.created_at,
        }


class Verifier(Protocol):
    @property
    def verifier_id(self) -> str: ...

    @property
    def cost(self) -> CostTier: ...

    def applies_to(self, artifact: Artifact) -> bool: ...

    def verify(self, artifact: Artifact) -> Evidence: ...


class UniversalVerifier:
    """
    El seam. Ejecuta los verificadores aplicables de barato a caro,
    corta en el primer FAIL, y aplica la regla asimétrica.
    """

    def __init__(self, verifiers: list[Verifier] | None = None) -> None:
        self._verifiers: list[Verifier] = list(verifiers or [])

    def register(self, verifier: Verifier) -> None:
        self._verifiers.append(verifier)

    def verify(self, artifact: Artifact) -> Evidence:
        applicable = [v for v in self._verifiers if v.applies_to(artifact)]
        cheaper = [v for v in applicable if v.cost < artifact.producer_cost]
        if not cheaper:
            return Evidence(
                verdict=Verdict.UNKNOWN,
                reason=(
                    "regla asimétrica: ningún verificador aplicable más barato "
                    f"que el productor ({artifact.producer_cost.name}); "
                    f"aplicables={[v.verifier_id for v in applicable]}"
                ),
            )

        checks: list[Check] = []
        verifier_ids: list[str] = []
        max_cost = CostTier.FREE
        for verifier in sorted(cheaper, key=lambda v: v.cost):
            evidence = verifier.verify(artifact)
            checks.extend(evidence.checks)
            verifier_ids.append(verifier.verifier_id)
            max_cost = max(max_cost, verifier.cost)
            if evidence.verdict is Verdict.FAIL:
                return Evidence(
                    verdict=Verdict.FAIL,
                    checks=tuple(checks),
                    total_cost=max_cost,
                    verifier_ids=tuple(verifier_ids),
                    reason=evidence.reason or f"{verifier.verifier_id} falló",
                )
            if evidence.verdict is Verdict.UNKNOWN:
                # Un verificador que no sabe no bloquea, pero queda registrado.
                checks.append(
                    Check(
                        name=f"{verifier.verifier_id}:unknown",
                        passed=True,
                        detail=evidence.reason,
                        cost=verifier.cost,
                    )
                )
        return Evidence(
            verdict=Verdict.PASS,
            checks=tuple(checks),
            total_cost=max_cost,
            verifier_ids=tuple(verifier_ids),
        )


# ---------------------------------------------------------------------------
# Adaptadores sobre lo que ya existe. Dependencias por Protocol e inyección:
# los tests usan fakes (sin red, sin subprocesos reales).
# ---------------------------------------------------------------------------


class _GuardLike(Protocol):
    def validate(self, code: str) -> Any: ...  # GuardResult: .valid, .violations


class StaticCodeVerifier:
    """ASTGuard sobre artefactos CODE con payload['code']."""

    def __init__(self, guard: _GuardLike) -> None:
        self._guard = guard

    @property
    def verifier_id(self) -> str:
        return "static_code"

    @property
    def cost(self) -> CostTier:
        return CostTier.STATIC

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.CODE and "code" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        result = self._guard.validate(str(artifact.payload["code"]))
        valid = bool(result.valid)
        detail = "; ".join(getattr(result, "violations", []) or [])
        check = Check(name="ast_guard", passed=valid, detail=detail, cost=self.cost)
        return Evidence(
            verdict=Verdict.PASS if valid else Verdict.FAIL,
            checks=(check,),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="" if valid else detail,
        )


class _AuditorLike(Protocol):
    def validate_output(self, snapshot: Any, output: Any) -> Any: ...  # ValidationResult


class OutputShapeVerifier:
    """ResultAuditor sobre COMMAND_OUTPUT con payload['snapshot'] y ['output']."""

    def __init__(self, auditor: _AuditorLike) -> None:
        self._auditor = auditor

    @property
    def verifier_id(self) -> str:
        return "output_shape"

    @property
    def cost(self) -> CostTier:
        return CostTier.SHAPE

    def applies_to(self, artifact: Artifact) -> bool:
        return (
            artifact.kind is ArtifactKind.COMMAND_OUTPUT
            and "snapshot" in artifact.payload
            and "output" in artifact.payload
        )

    def verify(self, artifact: Artifact) -> Evidence:
        result = self._auditor.validate_output(
            artifact.payload["snapshot"], artifact.payload["output"]
        )
        valid = bool(result.valid)
        detail = "; ".join(getattr(result, "reasons", ()) or ())
        check = Check(name="shape", passed=valid, detail=detail, cost=self.cost)
        return Evidence(
            verdict=Verdict.PASS if valid else Verdict.FAIL,
            checks=(check,),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="" if valid else detail,
        )


class _SandboxLike(Protocol):
    def execute(self, code: str, **kwargs: Any) -> Any: ...  # SandboxResult


class SandboxRunVerifier:
    """LayeredIsolationSandbox: ejecuta el código aislado y exige success."""

    def __init__(self, sandbox: _SandboxLike) -> None:
        self._sandbox = sandbox

    @property
    def verifier_id(self) -> str:
        return "sandbox_run"

    @property
    def cost(self) -> CostTier:
        return CostTier.SANDBOX

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.CODE and "code" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        result = self._sandbox.execute(str(artifact.payload["code"]))
        ok = bool(result.success)
        detail = "" if ok else (result.stderr or f"exit={result.exit_code}")
        check = Check(name="sandbox_exec", passed=ok, detail=detail[:500], cost=self.cost)
        return Evidence(
            verdict=Verdict.PASS if ok else Verdict.FAIL,
            checks=(check,),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="" if ok else detail[:500],
        )


class UnifiedDiffVerifier:
    """
    PATCH con payload['diff']: ¿es un diff unificado parseable y toca solo
    los paths permitidos (metadata['allowed_paths'])? Es la regla que el
    CodegenProposer imponía a mano, como verificador STATIC reutilizable.
    """

    _HEADER = re.compile(r"^(?:---|\+\+\+)\s+(?:[ab]/)?(\S+)", re.MULTILINE)
    _HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.MULTILINE)

    @property
    def verifier_id(self) -> str:
        return "unified_diff"

    @property
    def cost(self) -> CostTier:
        return CostTier.STATIC

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.PATCH and "diff" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        diff = str(artifact.payload["diff"])
        reasons: list[str] = []

        touched = {p for p in self._HEADER.findall(diff) if p != "/dev/null"}
        if not touched:
            reasons.append("sin cabeceras ---/+++ de diff unificado")
        if not self._HUNK.search(diff):
            reasons.append("sin hunks @@")

        allowed_raw = artifact.metadata.get("allowed_paths")
        if allowed_raw and touched:
            allowed = {str(p) for p in allowed_raw}
            extra = sorted(touched - allowed)
            if extra:
                reasons.append(f"toca paths fuera de los permitidos: {extra}")

        passed = not reasons
        detail = "; ".join(reasons)
        check = Check(name="unified_diff", passed=passed, detail=detail, cost=self.cost)
        return Evidence(
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            checks=(check,),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason=detail,
        )


class _RunnerLike(Protocol):
    def run(self) -> Any: ...  # ValidationReport: .passed, .errors


class SuiteVerifier:
    """
    ValidationRunner (suite + mypy) sobre PATCH. Hereda su guard
    anti-recursión: en tests SIEMPRE con runner fake inyectado.
    """

    def __init__(self, runner: _RunnerLike) -> None:
        self._runner = runner

    @property
    def verifier_id(self) -> str:
        return "suite"

    @property
    def cost(self) -> CostTier:
        return CostTier.SUITE

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.PATCH

    def verify(self, artifact: Artifact) -> Evidence:
        report = self._runner.run()
        passed = bool(report.passed)
        detail = "; ".join(getattr(report, "errors", []) or [])
        check = Check(name="suite_mypy", passed=passed, detail=detail, cost=self.cost)
        return Evidence(
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            checks=(check,),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
            reason="" if passed else detail,
        )
