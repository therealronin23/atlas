"""TwinDecider — wrapper shadow (Slice 3, G0.9 copia-digital).

Predice el veredicto de la decisión usando el corpus histórico (mayoría por kind).
NUNCA afecta al veredicto real: solo loggea la predicción y la compara contra el
veredicto del decisor base.

Invariantes:
- El veredicto devuelto es SIEMPRE el del inner_decider (firewall D).
- El predictor usa solo features públicas (kind, mutating, reversible).
- Warmup: con < MIN_CORPUS_SIZE registros, el predictor no predice.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Mapping

from atlas.core.decider.decision_record import DecisionRecord, DecisionSink
from atlas.core.decider.decider import DecisionAction, Decider, Verdict

logger = logging.getLogger(__name__)

MIN_CORPUS_SIZE = 30  # mínimo de registros para predicción estadísticamente útil


class ShadowAccuracyLog:
    """Acumula comparaciones predicción vs real en memoria (para métricas)."""

    def __init__(self) -> None:
        self._total = 0
        self._hits = 0

    def record(self, predicted: str, actual: str) -> None:
        self._total += 1
        if predicted == actual:
            self._hits += 1

    @property
    def total(self) -> int:
        return self._total

    @property
    def accuracy(self) -> float | None:
        """None si no hay suficientes muestras."""
        return self._hits / self._total if self._total > 0 else None


class ShadowPredictor:
    """Predictor de mayoría basado en corpus histórico.

    Para un DecisionAction dado, busca en el corpus todos los registros con el
    mismo (kind, mutating, reversible) y predice el veredicto mayoritario.
    Requiere al menos MIN_CORPUS_SIZE registros totales para activarse.
    """

    def predict(
        self, action: DecisionAction, corpus: list[DecisionRecord]
    ) -> str | None:
        """Predice el veredicto; devuelve None si corpus insuficiente o no hay datos."""
        # Excluir registros de resolución humana del entrenamiento
        training = [
            r for r in corpus
            if r.kind != "human_resolution" and r.verdict in ("Allow", "Deny")
        ]
        if len(training) < MIN_CORPUS_SIZE:
            return None
        # Filtrar por (kind, mutating, reversible) — las features más predictivas
        matches = [
            r for r in training
            if r.kind == action.kind
            and r.mutating == action.mutating
            and r.reversible == action.reversible
        ]
        if not matches:
            # Fallback: mayoría global (Allow/Deny)
            matches = training
        counts: Counter[str] = Counter(r.verdict for r in matches)
        return counts.most_common(1)[0][0]


class TwinDecider:
    """Wrapper shadow (G0.9, Slice 3): predice en paralelo pero nunca decide.

    El inner_decider decide; TwinDecider loggea la discrepancia. Cuando el corpus
    supera MIN_CORPUS_SIZE, la precisión del predictor se acumula en accuracy_log.
    """

    def __init__(
        self,
        inner_decider: Decider,
        corpus_sink: DecisionSink,
        *,
        accuracy_log: ShadowAccuracyLog | None = None,
    ) -> None:
        self._inner = inner_decider
        self._corpus_sink = corpus_sink
        self._predictor = ShadowPredictor()
        self._accuracy = accuracy_log or ShadowAccuracyLog()

    @property
    def accuracy_log(self) -> ShadowAccuracyLog:
        return self._accuracy

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict:
        # El veredicto real — NUNCA alterado
        real_verdict = self._inner.decide(action, sanctioned_intent, context)
        real_name = type(real_verdict).__name__

        # Shadow: predecir y comparar (solo si el corpus sink tiene lista de registros)
        corpus: list[DecisionRecord] = getattr(self._corpus_sink, "records", [])
        predicted = self._predictor.predict(action, corpus)
        if predicted is not None:
            self._accuracy.record(predicted, real_name)
            if predicted != real_name:
                logger.debug(
                    "TwinDecider shadow: kind=%s predicted=%s actual=%s accuracy=%.2f",
                    action.kind, predicted, real_name,
                    self._accuracy.accuracy or 0.0,
                )

        return real_verdict
