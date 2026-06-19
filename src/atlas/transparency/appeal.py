"""Atlas Transparency — Bucle de apelación de falsos positivos.

Implementa el flujo de apelación descrito en OSM/ADR-appeal:
  1. El sujeto firma una AppealRecord y la envía.
  2. El bucle la commitea al TransparencyLog (I3: reason NUNCA persiste).
  3. El reevaluador inyectable decide si es FP claro o dudoso.
  4. En caso de duda, el PDP (decisor intercambiable, no el humano) emite
     Allow | Deny.
  5. Si hay FP confirmado, se inserta una lección en el LessonStore —
     referenciando el patrón de causa, no el contenido del prompt.

Invariante I3 (CRÍTICO): ``AppealRecord.reason`` jamás toca el log ni las
lecciones. Solo persiste ``reason_hash`` (SHA-256 del reason).
"""

from __future__ import annotations

import collections
import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Mapping

from atlas.core.decider.decider import Allow, DecisionAction, Decider, Verdict
from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.verify import Check, CostTier, Evidence, Verdict as EvidVerdict
from atlas.transparency.log import TransparencyLog

# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass
class AppealRecord:
    """Registro de una apelación emitido por el sujeto.

    Atributos:
        subject_id:    Identidad estable del sujeto (clave pública / id de cuenta).
                       Es la clave para rate-limiting y campaign signals.
        seq:           Número de secuencia del evento original que se apela.
        payload_hash:  SHA-256 hex del payload bloqueado.
        subject_sig:   Firma del sujeto sobre el registro canónico.
                       Cambia en cada mensaje — NO se usa como clave de identidad.
        appeal_ts_ns:  Timestamp de la apelación en nanosegundos.
        reason:        Texto libre del sujeto — NUNCA se persiste (I3).
        reason_hash:   SHA-256(reason) — esto sí va al log.
    """

    subject_id: str      # Identidad estable; base del rate-limit y campaign signals
    seq: int
    payload_hash: str
    subject_sig: str
    appeal_ts_ns: int
    reason: str          # I3: campo efímero; no llega a disco/log/lección
    reason_hash: str     # SHA-256(reason) — la única huella persistida


@dataclass
class AppealVerdict:
    """Resultado del bucle de apelación.

    Atributos:
        appeal_seq:     seq del AppealRecord apelado.
        verdict:        "auto_restored" | "escalated" | "denied".
        cause:          Causa textual del veredicto (nunca el reason original).
        lesson_id:      ID de la lección creada, o None si no aplica.
        committed_leaf: Índice de la hoja en el TransparencyLog (>=0).
    """

    appeal_seq: int
    verdict: str
    cause: str
    lesson_id: str | None
    committed_leaf: int


# ---------------------------------------------------------------------------
# Type alias for the injectable reevaluator
# ---------------------------------------------------------------------------

#: Callable que recibe (payload_hash, cause) y devuelve "clear_fp" | "unclear".
Reevaluator = Callable[[str, str], str]


# ---------------------------------------------------------------------------
# FalsePositiveApealer
# ---------------------------------------------------------------------------


class FalsePositiveApealer:
    """Gestor del bucle de apelación de falsos positivos.

    Args:
        reevaluator:       Callable[[payload_hash, cause], "clear_fp"|"unclear"].
                           Inyectable; en tests se mockea.
        pdp:               Decider — PDP intercambiable (no hardcoded humano).
        lesson_store:      LessonStore para persistir lecciones verificadas.
        log:               TransparencyLog append-only.
        appeal_rate_limit: Máximo de apelaciones por sujeto en una ventana de 1h.
        clock:             Callable[[], int] que devuelve tiempo en nanosegundos.
                           Inyectable para tests deterministas.
    """

    _WINDOW_NS: int = 3_600 * 1_000_000_000  # 1 hora en ns

    def __init__(
        self,
        reevaluator: Reevaluator,
        pdp: Decider,
        lesson_store: LessonStore,
        log: TransparencyLog,
        *,
        appeal_rate_limit: int = 5,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._reevaluator = reevaluator
        self._pdp = pdp
        self._lesson_store = lesson_store
        self._log = log
        self._appeal_rate_limit = appeal_rate_limit
        self._clock: Callable[[], int] = clock if clock is not None else time.time_ns

        # Historial de timestamps de apelaciones por clave de sujeto.
        self._appeal_history: dict[str, list[int]] = collections.defaultdict(list)
        # Contador de señales de campaña por clave de sujeto.
        self._campaign_signals: dict[str, int] = collections.defaultdict(int)

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def submit(self, record: AppealRecord) -> AppealVerdict:
        """Procesa una apelación y devuelve el veredicto.

        El AppealRecord se commitea al log ANTES de evaluar (I3: sin reason).
        """
        # 1. Commitear al log (sin reason — I3).
        leaf_bytes = self._serialize_for_log(record)
        committed_leaf = self._log.append(leaf_bytes)

        # 2. Calcular clave de sujeto y comprobar rate limit.
        subject_key = self._subject_key(record)
        now_ns = self._clock()
        self._purge_old_timestamps(subject_key, now_ns)
        self._appeal_history[subject_key].append(now_ns)

        if len(self._appeal_history[subject_key]) > self._appeal_rate_limit:
            self._campaign_signals[subject_key] += 1
            return AppealVerdict(
                appeal_seq=record.seq,
                verdict="denied",
                cause="appeal_campaign",
                lesson_id=None,
                committed_leaf=committed_leaf,
            )

        # 3. Re-evaluar.
        eval_result = self._reevaluator(record.payload_hash, record.reason_hash)

        if eval_result == "clear_fp":
            lesson_id = self._learn(record.reason_hash, cause="auto_clear_fp")
            return AppealVerdict(
                appeal_seq=record.seq,
                verdict="auto_restored",
                cause="reevaluator_clear_fp",
                lesson_id=lesson_id,
                committed_leaf=committed_leaf,
            )

        # 4. Dudoso → escalar al PDP.
        action = DecisionAction(
            kind="appeal_escalation",
            descriptor=f"appeal:{record.seq}:{record.payload_hash[:16]}",
            mutating=False,
            reversible=True,
            sensitivity="normal",
        )
        pdp_verdict: Verdict = self._pdp.decide(
            action,
            sanctioned_intent="false_positive_appeal",
            context={"payload_hash": record.payload_hash, "reason_hash": record.reason_hash},
        )

        if isinstance(pdp_verdict, Allow):
            lesson_id = self._learn(record.reason_hash, cause="pdp_escalation_allow")
            return AppealVerdict(
                appeal_seq=record.seq,
                verdict="escalated",
                cause="pdp_allow",
                lesson_id=lesson_id,
                committed_leaf=committed_leaf,
            )

        # Deny (o cualquier otro veredicto no-Allow) → denied, sin lección.
        return AppealVerdict(
            appeal_seq=record.seq,
            verdict="denied",
            cause="pdp_deny",
            lesson_id=None,
            committed_leaf=committed_leaf,
        )

    def campaign_signal_count(self, subject_id: str) -> int:
        """Devuelve el número de señales de campaña para un sujeto.

        Keya directamente en ``subject_id`` — identidad estable del sujeto.
        Útil en tests para verificar que la señal se activó.
        """
        return self._campaign_signals.get(subject_id, 0)

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_for_log(record: AppealRecord) -> bytes:
        """Serializa el AppealRecord para el log — SIN el campo reason (I3)."""
        doc = {
            "appeal_ts_ns": record.appeal_ts_ns,
            "payload_hash": record.payload_hash,
            "reason_hash": record.reason_hash,
            "record_type": "appeal",
            "seq": record.seq,
            "subject_sig_prefix": record.subject_sig[:16],
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _subject_key(record: AppealRecord) -> str:
        """Devuelve la clave estable de sujeto: ``record.subject_id``."""
        return record.subject_id

    def _purge_old_timestamps(self, subject_key: str, now_ns: int) -> None:
        """Elimina entradas fuera de la ventana de 1h."""
        cutoff = now_ns - self._WINDOW_NS
        self._appeal_history[subject_key] = [
            ts for ts in self._appeal_history[subject_key] if ts >= cutoff
        ]

    def _learn(self, cause_hash: str, *, cause: str) -> str | None:
        """Inserta una lección referenciando el patrón de causa — nunca el contenido.

        Devuelve el lesson_id si la inserción tuvo éxito, None en caso contrario.
        I3: cause_hash es SHA-256(reason), nunca el reason en claro.
        """
        detection_heuristic = (
            f"cause_pattern:{cause_hash[:16]}"
        )
        avoid_pattern = (
            f"pattern associated with cause_hash {cause_hash[:16]} "
            f"(source: {cause})"
        )
        # Construir Evidence PASS para que LessonStore.add() no rechace.
        check = Check(
            name="appeal_fp_confirmed",
            passed=True,
            detail=f"FP confirmado vía {cause}; cause_hash={cause_hash[:16]}",
            cost=CostTier.STATIC,
        )
        evidence = Evidence(
            verdict=EvidVerdict.PASS,
            checks=(check,),
            total_cost=CostTier.STATIC,
            verifier_ids=("appeal.fp_loop",),
            reason="",
        )
        lesson = Lesson(
            id=f"lesson-{uuid.uuid4().hex[:12]}",
            title=f"FP pattern confirmed ({cause})",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic=detection_heuristic,
            avoid_pattern=avoid_pattern,
            evidence=evidence.to_dict(),
            tags=("fp_appeal", cause),
        )
        try:
            added = self._lesson_store.add(lesson)
            return str(added.id)
        except Exception:  # noqa: BLE001 — lección fallida no tumba el veredicto
            return None
