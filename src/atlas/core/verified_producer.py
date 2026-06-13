"""
Capa 3/ADR-048 — VerifiedProducer: el productor como lazo cerrado.

No es una función "LLM→diff y reza". Es un lazo cuyo JUEZ es evidencia barata
(capa 1), no la opinión del modelo:

    estimar → ground → [producir → verificar → (retar) → reflexionar]* → aprender

- **estimar** dificultad (capa 2): elige el productor más barato capaz.
- **ground** (capa 4): carga lecciones — avoid_pattern como restricción,
  heurística como check — en el contexto antes de producir.
- **producir** con el productor actual (determinista-arnés primero, LLM después).
- **verificar** en el seam de capa 1 ANTES de emitir nada.
- **retar**: si el diff pasa capa 1 y el gating lo pide, el panel adversarial
  lo ataca; una objeción sustantiva cuenta como fallo.
- **reflexionar**: la evidencia REAL del fallo (suite/sandbox/panel) vuelve como
  contexto y se escala de productor. No auto-crítica con otro LLM.
- **aprender**: el par fallo→éxito se ofrece como lección candidata (capa 4).

Seguridad: el `budget` (unidades de tier) corta el lazo — un lazo reflexivo sin
tope quema cómputo. Nada se aplica aquí; el resultado es un artefacto + veredicto
honesto que sube por el blackboard → decider.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from atlas.core.adversarial_panel import AdversarialPanel, should_convene
from atlas.core.verify import Artifact, ArtifactKind, Evidence, UniversalVerifier, Verdict
from atlas.router.cascade import (
    CostLedger,
    Difficulty,
    DifficultyEstimator,
    Producer,
    RuleBasedDifficultyEstimator,
    TaskSpec,
)


class GroundingSource(Protocol):
    """Capa 4: contexto de lecciones para una tarea. Devuelve (texto, ids)."""

    def context_for(self, spec: TaskSpec) -> tuple[str, tuple[str, ...]]: ...


class LearningSink(Protocol):
    """Capa 4: recibe el par fallo→éxito como lección candidata."""

    def record_cycle(
        self, spec: TaskSpec, *, failures: tuple[str, ...], success: bool
    ) -> None: ...


@dataclass(frozen=True)
class ProduceAttempt:
    producer_id: str
    verdict: Verdict
    stage: str          # "verify" | "panel"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_id": self.producer_id,
            "verdict": self.verdict.value,
            "stage": self.stage,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProduceOutcome:
    artifact: Artifact | None
    evidence: Evidence
    attempts: tuple[ProduceAttempt, ...]
    difficulty: Difficulty
    grounded_with: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.evidence.verdict is Verdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "difficulty": self.difficulty.name,
            "evidence": self.evidence.to_dict(),
            "attempts": [a.to_dict() for a in self.attempts],
            "grounded_with": list(self.grounded_with),
        }


class VerifiedProducer:
    def __init__(
        self,
        producers: list[Producer],
        verifier: UniversalVerifier,
        *,
        panel: AdversarialPanel | None = None,
        grounding: GroundingSource | None = None,
        learning: LearningSink | None = None,
        estimator: DifficultyEstimator | None = None,
        ledger: CostLedger | None = None,
        budget_units: int = 1000,
    ) -> None:
        self._producers = list(producers)
        self._verifier = verifier
        self._panel = panel
        self._grounding = grounding
        self._learning = learning
        self._estimator = estimator or RuleBasedDifficultyEstimator()
        self.ledger = ledger or CostLedger()
        self._budget = budget_units

    def produce(self, spec: TaskSpec) -> ProduceOutcome:
        difficulty = self._estimator.estimate(spec)
        ground_ctx, lesson_ids = (
            self._grounding.context_for(spec) if self._grounding else ("", ())
        )
        eligible = sorted(
            (p for p in self._producers if p.capability >= difficulty),
            key=lambda p: p.cost,
        )

        attempts: list[ProduceAttempt] = []
        failures: list[str] = []
        spent = 0
        artifact: Artifact | None = None
        evidence = Evidence(verdict=Verdict.UNKNOWN, reason="sin productor capaz")

        for producer in eligible:
            if spent >= self._budget:
                break
            # Reflexión: el contexto acumula grounding + la evidencia real de los
            # fallos previos. El productor escalado ve POR QUÉ falló el anterior.
            attempt_spec = self._with_context(spec, ground_ctx, failures)
            artifact = producer.produce(attempt_spec)
            if artifact.producer_cost is not producer.cost:
                artifact = replace(artifact, producer_cost=producer.cost)

            evidence = self._verifier.verify(artifact)
            self.ledger.record_attempt(producer.cost, evidence.total_cost)
            spent += int(producer.cost) + int(evidence.total_cost)
            if evidence.verdict is not Verdict.PASS:
                attempts.append(ProduceAttempt(producer.producer_id, evidence.verdict, "verify", evidence.reason))
                failures.append(f"[{producer.producer_id}] {evidence.reason}")
                continue

            # Capa 1 OK. Reto adversarial si el gating lo pide.
            panel_ev = self._maybe_panel(artifact, difficulty, spec, ground_ctx)
            if panel_ev is not None and panel_ev.verdict is not Verdict.PASS:
                attempts.append(ProduceAttempt(producer.producer_id, panel_ev.verdict, "panel", panel_ev.reason))
                failures.append(f"[panel/{producer.producer_id}] {panel_ev.reason}")
                evidence = panel_ev
                continue

            attempts.append(ProduceAttempt(producer.producer_id, Verdict.PASS, "panel" if panel_ev else "verify"))
            self.ledger.record_verified()
            self._record(spec, failures, success=True)
            return ProduceOutcome(artifact, evidence, tuple(attempts), difficulty, lesson_ids)

        self._record(spec, failures, success=False)
        return ProduceOutcome(artifact, evidence, tuple(attempts), difficulty, lesson_ids)

    # ------------------------------------------------------------------

    def _with_context(self, spec: TaskSpec, ground: str, failures: list[str]) -> TaskSpec:
        parts = [p for p in (spec.metadata.get("context", ""), ground) if p]
        if failures:
            parts.append("Intentos previos fallaron:\n" + "\n".join(failures))
        meta = {**spec.metadata, "context": "\n\n".join(parts)}
        return replace(spec, metadata=meta)

    def _maybe_panel(
        self, artifact: Artifact, difficulty: Difficulty, spec: TaskSpec, ground: str
    ) -> Evidence | None:
        if self._panel is None:
            return None
        risk = str(spec.metadata.get("risk", "medium"))
        irreversible = bool(spec.metadata.get("irreversible", False))
        if not should_convene(difficulty, risk, irreversible=irreversible):
            return None
        diff = str(artifact.payload.get("diff", artifact.payload.get("code", "")))
        return self._panel.verify(diff, ground)

    def _record(self, spec: TaskSpec, failures: list[str], *, success: bool) -> None:
        if self._learning is not None:
            self._learning.record_cycle(spec, failures=tuple(failures), success=success)
