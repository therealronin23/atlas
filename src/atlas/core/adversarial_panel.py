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
from atlas.core.verify import Artifact, ArtifactKind, Check, CostTier, Evidence, Verdict


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


class IrreversibleActionVerifier:
    """
    t1-irreversible-action-verifier (ADR-047) — verificador de
    `ArtifactKind.IRREVERSIBLE_ACTION`.

    Para una acción del mundo real sin camino de rollback (enviar un mensaje,
    publicar algo, hacer una oferta) no existe verificador determinista más
    barato que su productor: no hay sandbox ni test para "ya se envió". El
    verificador ES el `AdversarialPanel` ya existente (ADR-048), reusado tal
    cual — no se inventa un mecanismo de deliberación nuevo — pero con
    DISENSO OBLIGATORIO: cada reviewer recibe, además del contexto de la
    tarea, tres preguntas fijas que debe responder ("por qué esto es un
    error", "qué asume el plan que podría ser falso", "qué se rompe en el
    peor caso").

    Regla dura (aditiva, no relaja ningún gate HITL existente):
    - Consenso (panel → PASS) → procede, con la evidencia de disenso (los
      checks de cada reviewer respondiendo a las 3 preguntas) adjunta a la
      `Evidence` que sube.
    - Sin consenso (panel → FAIL por objeción sustantiva, o UNKNOWN por
      diversidad insuficiente) → el veredicto NO se convierte en PASS bajo
      ninguna circunstancia; sube tal cual para que el decisor
      (autonomous_decider/hybrid_decider) escale al humano — nunca se
      auto-aprueba una acción irreversible.
    """

    _DISSENT_QUESTIONS = (
        "¿Por qué esto es un error?",
        "¿Qué asume el plan que podría ser falso?",
        "¿Qué se rompe en el peor caso?",
    )

    def __init__(self, panel: AdversarialPanel) -> None:
        self._panel = panel

    @property
    def verifier_id(self) -> str:
        return "irreversible_action_panel"

    @property
    def cost(self) -> CostTier:
        return CostTier.MODEL

    def applies_to(self, artifact: Artifact) -> bool:
        return artifact.kind is ArtifactKind.IRREVERSIBLE_ACTION

    def verify(self, artifact: Artifact) -> Evidence:
        action = str(artifact.payload.get("action", ""))
        context = self._dissent_context(str(artifact.payload.get("context", "")))
        evidence = self._panel.verify(action, context)

        if evidence.verdict is Verdict.PASS:
            reason = evidence.reason
        else:
            # Sin consenso: nunca se auto-aprueba. El motivo deja explícito
            # que esto escala al humano, no que se rechaza en silencio.
            reason = (
                evidence.reason
                or "panel adversarial sin diversidad suficiente"
            ) + " — escala al humano, no se auto-aprueba"

        return Evidence(
            verdict=evidence.verdict,
            checks=evidence.checks,
            total_cost=evidence.total_cost,
            verifier_ids=(self.verifier_id,) + evidence.verifier_ids,
            reason=reason,
        )

    @classmethod
    def _dissent_context(cls, base_context: str) -> str:
        questions = "\n".join(f"- {q}" for q in cls._DISSENT_QUESTIONS)
        block = f"DISENSO OBLIGATORIO — responde explícitamente:\n{questions}"
        return f"{base_context}\n\n{block}" if base_context else block
