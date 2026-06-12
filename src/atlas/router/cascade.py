"""
Capa 2 — Cascada con routing por dificultad y verificabilidad (ADR-042).

Lo mecánico-verificable baja a producers baratos (modelos pequeños/locales);
lo difícil sube a frontier. NADA sube sin pasar por el seam de la capa 1
(`UniversalVerifier`): un FAIL o UNKNOWN escala al siguiente producer, y
escalar sube `producer_cost`, lo que puede habilitar más verificadores por
la regla asimétrica — la cascada y la regla cooperan.

Ortogonal al Classifier de seguridad (que decide *si* y *dónde*) y al
Decider (que asigna políticas, no aprueba escaladas: si aprobara cada
intento sería HITL con otro nombre). Métrica de éxito de la capa:
coste por resultado verificado (`CostLedger`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Any, Protocol

from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    CostTier,
    Evidence,
    UniversalVerifier,
    Verdict,
)


class Difficulty(IntEnum):
    MECHANICAL = 0
    STANDARD = 1
    HARD = 2


@dataclass(frozen=True)
class TaskSpec:
    intent: str
    kind: ArtifactKind
    metadata: dict[str, Any] = field(default_factory=dict)


class Producer(Protocol):
    @property
    def producer_id(self) -> str: ...

    @property
    def cost(self) -> CostTier: ...

    @property
    def capability(self) -> Difficulty: ...

    def produce(self, spec: TaskSpec) -> Artifact: ...


class DifficultyEstimator(Protocol):
    def estimate(self, spec: TaskSpec) -> Difficulty: ...


# Patrones del estimador por defecto. El SLMClassifier podrá entrar como
# otra implementación del Protocol cuando haya evidencia de que lo necesita.
_MECHANICAL_PATTERNS = [
    r"\b(renombra|rename|formatea|format|reordena|sort)\b",
    r"\b(regex|sustituye|replace|busca y reemplaza)\b",
    r"\b(typo|errata|docstring|comentario)\b",
    r"\bbump\b|\bversion\b",
]
_HARD_PATTERNS = [
    r"\b(diseña|design|arquitectura|architecture|refactor global)\b",
    r"\b(decide|trade-?off|estrategia|strategy)\b",
    r"\b(ambig|no s[eé]|unclear|investiga|research)\b",
    r"\b(seguridad|security|threat|crypto)\b",
]


class RuleBasedDifficultyEstimator:
    def __init__(self) -> None:
        self._mechanical = [re.compile(p, re.IGNORECASE) for p in _MECHANICAL_PATTERNS]
        self._hard = [re.compile(p, re.IGNORECASE) for p in _HARD_PATTERNS]

    def estimate(self, spec: TaskSpec) -> Difficulty:
        # HARD primero: ante señales mixtas, mejor pagar de más que
        # verificar de menos.
        for pat in self._hard:
            if pat.search(spec.intent):
                return Difficulty.HARD
        for pat in self._mechanical:
            if pat.search(spec.intent):
                return Difficulty.MECHANICAL
        return Difficulty.STANDARD


@dataclass(frozen=True)
class Attempt:
    producer_id: str
    producer_cost: CostTier
    verdict: Verdict
    evidence: Evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_id": self.producer_id,
            "producer_cost": self.producer_cost.name,
            "verdict": self.verdict.value,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class CascadeResult:
    spec: TaskSpec
    artifact: Artifact | None
    evidence: Evidence
    attempts: tuple[Attempt, ...]
    difficulty: Difficulty

    @property
    def verified(self) -> bool:
        return self.evidence.verdict is Verdict.PASS

    @property
    def escalations(self) -> int:
        return max(0, len(self.attempts) - 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.spec.intent,
            "kind": self.spec.kind.value,
            "difficulty": self.difficulty.name,
            "verified": self.verified,
            "escalations": self.escalations,
            "evidence": self.evidence.to_dict(),
            "attempts": [a.to_dict() for a in self.attempts],
        }


class CostLedger:
    """
    Contabilidad en unidades ordinales de tier (CostTier.value). No son
    euros: sirven para comparar políticas de routing entre sí, no para
    facturar. La capa 2 puede mapear tier→coste real cuando haya datos.
    """

    def __init__(self) -> None:
        self._spent_units = 0
        self._verified = 0
        self._attempts = 0

    def record_attempt(self, producer_cost: CostTier, verify_cost: CostTier) -> None:
        self._spent_units += int(producer_cost) + int(verify_cost)
        self._attempts += 1

    def record_verified(self) -> None:
        self._verified += 1

    @property
    def spent_units(self) -> int:
        return self._spent_units

    @property
    def verified_count(self) -> int:
        return self._verified

    @property
    def attempt_count(self) -> int:
        return self._attempts

    def cost_per_verified_result(self) -> float | None:
        if self._verified == 0:
            return None
        return self._spent_units / self._verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "spent_units": self._spent_units,
            "verified_count": self._verified,
            "attempt_count": self._attempts,
            "cost_per_verified_result": self.cost_per_verified_result(),
        }


class CascadeRouter:
    """
    Elige el producer más barato con capability suficiente, verifica con
    la capa 1, y escala en FAIL/UNKNOWN. Agotados los producers devuelve
    el último veredicto real — nunca un PASS fingido.
    """

    def __init__(
        self,
        verifier: UniversalVerifier,
        producers: list[Producer],
        *,
        estimator: DifficultyEstimator | None = None,
        ledger: CostLedger | None = None,
    ) -> None:
        self._verifier = verifier
        self._producers = list(producers)
        self._estimator = estimator or RuleBasedDifficultyEstimator()
        self.ledger = ledger or CostLedger()

    def route(self, spec: TaskSpec) -> CascadeResult:
        if spec.metadata.get("governance_blocked"):
            # El Classifier de seguridad decide upstream; esto es el cinturón.
            raise ValueError(
                f"spec bloqueado por governance no entra en la cascada: {spec.intent!r}"
            )

        difficulty = self._estimator.estimate(spec)
        eligible = sorted(
            (p for p in self._producers if p.capability >= difficulty),
            key=lambda p: p.cost,
        )
        if not eligible:
            return CascadeResult(
                spec=spec,
                artifact=None,
                evidence=Evidence(
                    verdict=Verdict.UNKNOWN,
                    reason=f"sin producer con capability >= {difficulty.name}",
                ),
                attempts=(),
                difficulty=difficulty,
            )

        attempts: list[Attempt] = []
        artifact: Artifact | None = None
        evidence = Evidence(verdict=Verdict.UNKNOWN, reason="sin intentos")
        for producer in eligible:
            artifact = producer.produce(spec)
            if artifact.producer_cost is not producer.cost:
                # La regla asimétrica compara contra el coste REAL del
                # productor; un artifact que se declara más barato la burla.
                artifact = replace(artifact, producer_cost=producer.cost)
            evidence = self._verifier.verify(artifact)
            attempts.append(
                Attempt(
                    producer_id=producer.producer_id,
                    producer_cost=producer.cost,
                    verdict=evidence.verdict,
                    evidence=evidence,
                )
            )
            self.ledger.record_attempt(producer.cost, evidence.total_cost)
            if evidence.verdict is Verdict.PASS:
                self.ledger.record_verified()
                break

        return CascadeResult(
            spec=spec,
            artifact=artifact,
            evidence=evidence,
            attempts=tuple(attempts),
            difficulty=difficulty,
        )


# ---------------------------------------------------------------------------
# Adaptador InferenceHub → cascada. Dependencia por Protocol e inyección:
# en tests, hub fake (sin red).
# ---------------------------------------------------------------------------


class _HubLike(Protocol):
    def infer(self, request: Any) -> Any: ...  # InferenceRequest -> InferenceResponse


class InferenceProducer:
    """Un rung de la cascada respaldado por InferenceHub a un nivel fijo."""

    def __init__(
        self,
        hub: _HubLike,
        *,
        level: Any,  # InferenceLevel; Any evita import circular core<->router
        capability: Difficulty,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> None:
        from atlas.core.inference_hub import InferenceLevel

        self._hub = hub
        self._level = level
        self._capability = capability
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._cost = (
            CostTier.FRONTIER if level is InferenceLevel.L2 else CostTier.MODEL
        )

    @property
    def producer_id(self) -> str:
        return f"inference:{getattr(self._level, 'value', self._level)}"

    @property
    def cost(self) -> CostTier:
        return self._cost

    @property
    def capability(self) -> Difficulty:
        return self._capability

    def produce(self, spec: TaskSpec) -> Artifact:
        from atlas.core.inference_hub import InferenceRequest

        response = self._hub.infer(
            InferenceRequest(
                prompt=spec.intent,
                level=self._level,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                context=str(spec.metadata.get("context", "")),
                task_id=str(spec.metadata.get("task_id", "")) or None,
            )
        )
        payload: dict[str, Any] = {"text": response.text}
        if spec.kind in (ArtifactKind.CODE, ArtifactKind.PATCH):
            payload["code" if spec.kind is ArtifactKind.CODE else "diff"] = response.text
        return Artifact(
            kind=spec.kind,
            payload=payload,
            producer_cost=self._cost,
            # spec.metadata se propaga: los verificadores leen del artifact
            # (p.ej. allowed_paths en UnifiedDiffVerifier).
            metadata={
                **spec.metadata,
                "provider": response.provider,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "success": response.success,
                "mode": response.mode,
            },
        )
