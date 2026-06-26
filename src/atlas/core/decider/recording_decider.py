"""RecordingDecider — wrapper transparente del Decider Protocol (slice 1 copia-digital).

Intercepta cada llamada a decide(), graba un DecisionRecord al sink (best-effort),
y devuelve el veredicto del inner intacto. No expone lectura del corpus (firewall D).

Correcciones del Cónclave incorporadas:
  A — split features/rationale (shredeable por separado)
  B — decider_version (code-hash del módulo del decisor)
  D — wrapper solo-escritura; NADA del corpus realimenta la decisión
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
import time
from collections.abc import Mapping
from typing import Callable

from atlas.core.decider.decision_record import DecisionRecord, DecisionSink
from atlas.core.decider.decider import (
    Allow,
    DecisionAction,
    Decider,
    Deny,
    RequiresHuman,
    Verdict,
    action_hash,
)

logger = logging.getLogger(__name__)


def _module_version(obj: object) -> str:
    """Hash corto del código fuente del módulo donde vive el objeto.

    Corrección B: el decider_version permite detectar deriva entre el corpus
    grabado bajo versión X y la versión Y que evalúa en shadow.
    """
    try:
        mod = inspect.getmodule(type(obj))
        src = inspect.getsource(mod) if mod else ""
        return hashlib.sha256(src.encode()).hexdigest()[:12]
    except Exception:
        return "unknown"


def _verdict_name(verdict: Verdict) -> str:
    return type(verdict).__name__


class RecordingDecider:
    """Wrapper transparente — graba cada decisión, no altera el veredicto.

    Invariantes (firewall D por construcción):
    - No tiene método de lectura del corpus.
    - El corpus grabado NUNCA influye en self._inner.decide().
    - Si el sink falla, se loggea y la decisión procede (best-effort).
    """

    def __init__(
        self,
        inner: Decider,
        sink: DecisionSink,
        *,
        decider_version: str | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._inner = inner
        self._sink = sink
        self._decider_name = type(inner).__name__
        self._decider_version = decider_version or _module_version(inner)
        self._clock = clock

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict:
        verdict = self._inner.decide(action, sanctioned_intent, context)

        rec = DecisionRecord(
            record_id=action_hash(action, sanctioned_intent),
            action_hash_val=action_hash(action, sanctioned_intent),
            kind=action.kind,
            descriptor=action.descriptor,
            mutating=action.mutating,
            reversible=action.reversible,
            sensitivity=action.sensitivity,
            requires_approval=action.requires_approval,
            verdict=_verdict_name(verdict),
            decider_name=self._decider_name,
            decider_version=self._decider_version,
            timestamp_ns=self._clock(),
            rationale=str(context.get("rationale")) if context.get("rationale") else None,
        )

        try:
            self._sink.record(rec)
        except Exception as exc:
            logger.warning("RecordingDecider: sink failed (best-effort), ignoring: %s", exc)

        return verdict
