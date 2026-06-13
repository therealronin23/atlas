"""
Capa 3/ADR-047 — Panel adversarial (abogado del diablo).

Antes de una acción/diff no trivial, N revisores con prompts HOSTILES atacan el
artefacto ("¿qué rompe esto?", "¿qué asume que es falso?", "¿qué caso límite
ignora?"). Produce `Evidence` (tipo de capa 1): PASS = sobrevivió; FAIL = hay
objeción sustantiva, escala al humano.

Dos disciplinas, aprendidas de esta casa:

- **Diversidad obligatoria**: los revisores deben venir de proveedores
  DISTINTOS. Un panel de tres llamadas al mismo modelo no es un panel — es la
  misma opinión tres veces. Sin diversidad mínima el veredicto es UNKNOWN
  (no puede certificar; unknown > mentir).
- **Gating**: convocar modelos para debatir un typo es absurdo. El panel solo
  entra por encima de un umbral (irreversible / alto riesgo / difícil). Lo
  trivial-determinista lo salta.

Los revisores se inyectan (Protocol); en tests, fakes — sin LLM real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

from atlas.router.cascade import Difficulty
from atlas.core.verify import Check, CostTier, Evidence, Verdict


class Severity(IntEnum):
    NONE = 0     # sin objeción
    MINOR = 1    # matiz, no bloquea
    MAJOR = 2    # objeción sustantiva
    BLOCKING = 3 # error claro


@dataclass(frozen=True)
class Objection:
    reviewer_id: str
    provider: str
    severity: Severity
    detail: str = ""


class Reviewer(Protocol):
    @property
    def reviewer_id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    def review(self, diff: str, context: str = "") -> Objection: ...


def should_convene(
    difficulty: Difficulty,
    risk: str,
    *,
    irreversible: bool = False,
) -> bool:
    """Gating: el panel se convoca para lo irreversible, lo de alto riesgo o lo
    difícil. Lo trivial-mecánico-reversible lo salta (no malgastar modelos)."""
    if irreversible:
        return True
    if risk in {"high", "critical"}:
        return True
    return difficulty >= Difficulty.HARD


class AdversarialPanel:
    """Convoca revisores diversos y agrega sus objeciones a una `Evidence`."""

    def __init__(
        self,
        reviewers: list[Reviewer],
        *,
        min_providers: int = 2,
        block_at: Severity = Severity.MAJOR,
    ) -> None:
        self._reviewers = list(reviewers)
        self._min_providers = min_providers
        self._block_at = block_at

    def verify(self, diff: str, context: str = "") -> Evidence:
        providers = {r.provider for r in self._reviewers}
        if len(providers) < self._min_providers:
            return Evidence(
                verdict=Verdict.UNKNOWN,
                total_cost=CostTier.MODEL,
                reason=(
                    f"diversidad insuficiente: {len(providers)} proveedor(es) "
                    f"distinto(s), se exigen {self._min_providers} — el panel no "
                    "puede certificar"
                ),
            )

        checks: list[Check] = []
        blocking: list[Objection] = []
        for reviewer in self._reviewers:
            objection = reviewer.review(diff, context)
            substantive = objection.severity >= self._block_at
            checks.append(
                Check(
                    name=f"{reviewer.reviewer_id}@{reviewer.provider}",
                    passed=not substantive,
                    detail=f"[{objection.severity.name}] {objection.detail}".strip(),
                    cost=CostTier.MODEL,
                )
            )
            if substantive:
                blocking.append(objection)

        if blocking:
            reason = "; ".join(
                f"{o.reviewer_id}: {o.detail}" for o in blocking
            )
            return Evidence(
                verdict=Verdict.FAIL,
                checks=tuple(checks),
                total_cost=CostTier.MODEL,
                verifier_ids=("adversarial_panel",),
                reason=reason,
            )
        return Evidence(
            verdict=Verdict.PASS,
            checks=tuple(checks),
            total_cost=CostTier.MODEL,
            verifier_ids=("adversarial_panel",),
        )
