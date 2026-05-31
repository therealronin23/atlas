"""Clasificación híbrida rule-based + SLM con política de empate.

Extraído de ``Orchestrator`` (refactor god-object slice 6, 2026-05-31).
Sin cambios de comportamiento — solo movimiento físico.

Responsabilidad única: combinar el clasificador determinista (rule-based) con
el SLM, aplicar la política de desempate (el SLM gana solo si propone una ruta
más específica que LOCAL_SAFE o mayor confidence) y la red de seguridad que
degrada un BLOCKED alucinado del SLM cuando el rule no vio peligro. Cada consulta
al SLM y cada override queda auditado en Merkle.

El SLM se inyecta vía getter (``slm_getter``) porque ``Orchestrator`` lo
construye de forma perezosa y puede reasignarlo después del __init__.
"""

from __future__ import annotations

from typing import Callable

from atlas.core.contracts import RoutingLevel
from atlas.logging.merkle_logger import MerkleLogger
from atlas.router.classifier import ClassificationResult, Classifier
from atlas.router.slm_classifier import SLMClassifier


class HybridClassifier:
    """Rule-based + SLM con desempate y red de seguridad anti-alucinación."""

    def __init__(
        self,
        *,
        rule_classifier: Classifier,
        slm_getter: Callable[[], SLMClassifier | None],
        merkle: MerkleLogger,
        bypass_threshold: float,
    ) -> None:
        self._rule = rule_classifier
        self._slm_getter = slm_getter
        self._merkle = merkle
        self._bypass_threshold = bypass_threshold

    def classify(
        self, intent: str, sensitivity: str | None, *, task_id: str | None = None,
    ) -> ClassificationResult:
        """
        Combina rule-based + SLM con politica de empate refinada:

        1. rule-based corre primero (microsegundos, sin red).
        2. Si governance_blocked OR confidence >= bypass_threshold (1.0)
           -> se confia en el rule, no se consulta SLM.
        3. Si el rule cae al default LOCAL_SAFE -> se consulta SLM. El SLM
           gana el empate cuando identifica una ruta MAS ESPECIFICA que
           LOCAL_SAFE (incluso con la misma confidence) o cuando su
           confidence es estrictamente mayor.

        Cada consulta al SLM y el ganador final quedan registrados en
        MerkleLogger para metricas.
        """
        rule = self._rule.classify(intent, sensitivity=sensitivity or "default")
        if rule.governance_blocked or rule.confidence >= self._bypass_threshold:
            return rule

        slm_classifier = self._slm_getter()
        assert slm_classifier is not None
        slm = slm_classifier.classify(intent)
        self._merkle.log(
            action="classify.slm_consulted",
            agent="classifier_hybrid",
            result="success",
            risk_level="safe",
            payload={
                "rule_level":      rule.level.value,
                "rule_confidence": rule.confidence,
                "slm_level":       slm.level.value,
                "slm_confidence":  slm.confidence,
                "slm_mode":        slm.mode,
                "slm_reason":      slm.reason,
            },
            task_id=task_id,
        )

        slm_wins = (
            slm.confidence > rule.confidence
            or (
                slm.level != RoutingLevel.LOCAL_SAFE
                and slm.confidence >= rule.confidence
            )
        )
        if not slm_wins:
            return rule

        # Safety net: only trust the SLM's BLOCKED verdict when the
        # rule-based classifier ALSO suspects something. The rule classifier
        # is deterministic and catches the real constitutional violations
        # (sudo, rm -rf, governance edits). If the rule says "Sin patron
        # especifico" (default LOCAL_SAFE) but the SLM hallucinates BLOCKED
        # for an ambiguous/conversational intent, we degrade to LOCAL_SAFE
        # to avoid bricking the bot on greetings or chitchat.
        if slm.level == RoutingLevel.BLOCKED and rule.level == RoutingLevel.LOCAL_SAFE:
            self._merkle.log(
                action="classify.slm_blocked_overridden",
                agent="classifier_hybrid",
                result="downgraded_to_local_safe",
                risk_level="safe",
                payload={
                    "slm_reason": slm.reason,
                    "rule_reason": rule.reason,
                },
                task_id=task_id,
            )
            return ClassificationResult(
                level=RoutingLevel.LOCAL_SAFE,
                confidence=max(slm.confidence, rule.confidence),
                matched_pattern=None,
                governance_blocked=False,
                reason=(
                    f"SLM proposed BLOCKED but rule classifier saw no danger; "
                    f"downgraded to LOCAL_SAFE. SLM: {slm.reason}"
                ),
            )

        return ClassificationResult(
            level=slm.level,
            confidence=slm.confidence,
            matched_pattern=None,
            governance_blocked=(slm.level == RoutingLevel.BLOCKED),
            reason=f"SLM: {slm.reason} (rule default: {rule.reason})",
        )
