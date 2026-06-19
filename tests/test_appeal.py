"""Tests for FalsePositiveApealer (ADR-appeal, I3 invariant).

TDD suite: 5 scenarios covering the main verdict branches, rate-limiting,
and the commitment invariant. TransparencyLog is used in-memory (no path).
Reevaluator and PDP are simple stubs — no subprocesses, no GUI.
"""
from __future__ import annotations

import time
from typing import Mapping
from unittest.mock import MagicMock

import pytest

from atlas.core.decider.decider import Allow, DecisionAction, Deny
from atlas.security.authorization import HMACSigner
from atlas.transparency.appeal import AppealRecord, AppealVerdict, FalsePositiveApealer
from atlas.transparency.log import TransparencyLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY = b"appeal-test-key-32bytes-padding!!"


def _make_log() -> TransparencyLog:
    return TransparencyLog(HMACSigner(_KEY))


def _make_record(
    seq: int = 0,
    subject_prefix: str = "aaa",
    subject_id: str = "subject-default",
    subject_sig: str | None = None,
) -> AppealRecord:
    sig = subject_sig if subject_sig is not None else (
        f"{subject_prefix}XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    )
    return AppealRecord(
        subject_id=subject_id,
        seq=seq,
        payload_hash="deadbeef" * 8,
        subject_sig=sig,
        appeal_ts_ns=time.time_ns(),
        reason="the model blocked my legitimate question about astronomy",
        reason_hash="a" * 64,  # SHA-256 placeholder; exact value not enforced here
    )


def _pdp_allow(_action: DecisionAction, _intent: str, _ctx: Mapping[str, object]) -> Allow:
    return Allow(reason="fp confirmed by pdp")


def _pdp_deny(_action: DecisionAction, _intent: str, _ctx: Mapping[str, object]) -> Deny:
    return Deny(reason="not a fp")


# ---------------------------------------------------------------------------
# T1 — clear FP: reevaluator→"clear_fp" ⇒ "auto_restored" + lesson_id
# ---------------------------------------------------------------------------

def test_t1_clear_fp_auto_restored() -> None:
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-abc123")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    pdp.decide.side_effect = AssertionError("should not reach pdp on clear_fp")

    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)
    record = _make_record()
    verdict = appealer.submit(record)

    assert verdict.verdict == "auto_restored"
    assert verdict.lesson_id is not None
    assert verdict.committed_leaf >= 0


# ---------------------------------------------------------------------------
# T2 — duda→escala: reevaluator→"unclear", PDP→Allow ⇒ "escalated"
# ---------------------------------------------------------------------------

def test_t2_unclear_pdp_allow_escalated() -> None:
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-xyz789")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "unclear"

    pdp = MagicMock()
    pdp.decide.return_value = Allow(reason="escalated allow")

    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)
    verdict = appealer.submit(_make_record())

    assert verdict.verdict == "escalated"
    assert verdict.committed_leaf >= 0


# ---------------------------------------------------------------------------
# T3 — abuso: 6 apelaciones del mismo sujeto en <1h ⇒ la 6ª denied + señal
# ---------------------------------------------------------------------------

def test_t3_rate_limit_campaign_signal() -> None:
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-aaa")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    pdp.decide.return_value = Allow()

    # Use a fixed clock so all 6 appeals land within the same 1-hour window.
    fixed_ns = time.time_ns()

    def fixed_clock() -> int:
        return fixed_ns

    appealer = FalsePositiveApealer(
        reevaluator, pdp, lesson_store, log,
        appeal_rate_limit=5,
        clock=fixed_clock,
    )

    same_subject_id = "subject-bbb"
    verdicts = []
    for i in range(6):
        r = _make_record(seq=i, subject_prefix="bbb", subject_id=same_subject_id)
        verdicts.append(appealer.submit(r))

    # First 5 must pass through (auto_restored)
    for v in verdicts[:5]:
        assert v.verdict == "auto_restored", f"expected auto_restored, got {v.verdict}"

    # 6th must be denied with campaign cause
    sixth = verdicts[5]
    assert sixth.verdict == "denied"
    assert sixth.cause == "appeal_campaign"
    # Campaign signal must be set
    assert appealer.campaign_signal_count(same_subject_id) >= 1


# ---------------------------------------------------------------------------
# T4 — TP real: reevaluator→"unclear", PDP→Deny ⇒ "denied", lesson_id None
# ---------------------------------------------------------------------------

def test_t4_true_positive_denied() -> None:
    log = _make_log()
    lesson_store = MagicMock()

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "unclear"

    pdp = MagicMock()
    pdp.decide.return_value = Deny(reason="genuine block")

    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)
    verdict = appealer.submit(_make_record())

    assert verdict.verdict == "denied"
    assert verdict.lesson_id is None
    assert verdict.committed_leaf >= 0


# ---------------------------------------------------------------------------
# T5 — commitment: any verdict ⇒ committed_leaf >= 0 and log grew
# ---------------------------------------------------------------------------

def test_t5_commitment_log_grows() -> None:
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-grow")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()

    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)

    size_before = log.tree_size
    record = _make_record()
    verdict = appealer.submit(record)

    assert verdict.committed_leaf >= 0
    assert log.tree_size == size_before + 1
    assert log.tree_size > 0


# ---------------------------------------------------------------------------
# I3 invariant: reason field is never stored in the record committed to the log
# ---------------------------------------------------------------------------

def test_i3_reason_not_in_log_entry() -> None:
    """The raw reason text must never appear in the bytes committed to the log."""
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-i3")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)

    secret_reason = "my-very-secret-reason-text-xyz"
    record = AppealRecord(
        subject_id="subject-i3",
        seq=0,
        payload_hash="aa" * 32,
        subject_sig="cc" * 32,
        appeal_ts_ns=time.time_ns(),
        reason=secret_reason,
        reason_hash="bb" * 32,
    )
    appealer.submit(record)

    # Inspect all log entries — reason must not appear
    for entry in log._entries:  # noqa: SLF001 — white-box test for I3
        assert secret_reason.encode() not in entry


# ---------------------------------------------------------------------------
# T7 — mismo subject_id, firmas distintas → mismo bucket de rate-limit
# (esto fallaría con subject_sig[:3] porque cada firma es diferente)
# ---------------------------------------------------------------------------

def test_t7_same_subject_id_different_sigs_same_bucket() -> None:
    """Un mismo subject_id con firmas distintas en cada apelación debe acumular
    hacia el mismo bucket de rate-limit.  La 6ª apelación debe ser denegada."""
    import uuid

    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-t7")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    pdp.decide.return_value = Allow()

    fixed_ns = time.time_ns()

    def fixed_clock() -> int:
        return fixed_ns

    appealer = FalsePositiveApealer(
        reevaluator, pdp, lesson_store, log,
        appeal_rate_limit=5,
        clock=fixed_clock,
    )

    stable_subject_id = "subject-stable-id-xyz"
    verdicts = []
    for i in range(6):
        # Each call uses a completely different subject_sig (simulates real usage
        # where the signature covers the appeal content and thus changes each time).
        unique_sig = uuid.uuid4().hex * 2  # 64-char unique string per appeal
        r = _make_record(seq=i, subject_id=stable_subject_id, subject_sig=unique_sig)
        verdicts.append(appealer.submit(r))

    for v in verdicts[:5]:
        assert v.verdict == "auto_restored", f"expected auto_restored, got {v.verdict}"

    sixth = verdicts[5]
    assert sixth.verdict == "denied", f"expected denied, got {sixth.verdict}"
    assert sixth.cause == "appeal_campaign"
    assert appealer.campaign_signal_count(stable_subject_id) >= 1


# ---------------------------------------------------------------------------
# T8 — dos subject_id distintos no colisionan
# ---------------------------------------------------------------------------

def test_t8_different_subject_ids_no_collision() -> None:
    """5 apelaciones de cada uno de dos sujetos distintos no deben disparar campaña."""
    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-t8")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    pdp.decide.return_value = Allow()

    fixed_ns = time.time_ns()

    def fixed_clock() -> int:
        return fixed_ns

    appealer = FalsePositiveApealer(
        reevaluator, pdp, lesson_store, log,
        appeal_rate_limit=5,
        clock=fixed_clock,
    )

    id_alice = "subject-alice"
    id_bob = "subject-bob"

    for i in range(5):
        va = appealer.submit(_make_record(seq=i, subject_id=id_alice))
        vb = appealer.submit(_make_record(seq=100 + i, subject_id=id_bob))
        assert va.verdict == "auto_restored", f"Alice appeal {i} denied unexpectedly"
        assert vb.verdict == "auto_restored", f"Bob appeal {i} denied unexpectedly"

    assert appealer.campaign_signal_count(id_alice) == 0
    assert appealer.campaign_signal_count(id_bob) == 0


# ---------------------------------------------------------------------------
# T9 — wiring: TransparencyGateway.submit_appeal delega en el appealer
# ---------------------------------------------------------------------------

def test_t9_gateway_submit_appeal_delegates() -> None:
    from atlas.transparency.client_cosign import ClientCosigner
    from atlas.transparency.gateway import TransparencyGateway

    log = _make_log()
    lesson_store = MagicMock()
    lesson_store.add.return_value = MagicMock(id="lesson-wire1")

    def reevaluator(payload_hash: str, cause: str) -> str:
        return "clear_fp"

    pdp = MagicMock()
    appealer = FalsePositiveApealer(reevaluator, pdp, lesson_store, log)

    cosigner = ClientCosigner(HMACSigner(_KEY))
    gw = TransparencyGateway(cosigner, HMACSigner(_KEY), log, appealer=appealer)

    verdict = gw.submit_appeal(_make_record())
    assert verdict.verdict == "auto_restored"
    assert verdict.committed_leaf >= 0


# ---------------------------------------------------------------------------
# T10 — wiring fail-closed: sin appealer, submit_appeal lanza RuntimeError
# ---------------------------------------------------------------------------

def test_t10_gateway_no_appealer_fail_closed() -> None:
    from atlas.transparency.client_cosign import ClientCosigner
    from atlas.transparency.gateway import TransparencyGateway

    log = _make_log()
    cosigner = ClientCosigner(HMACSigner(_KEY))
    gw = TransparencyGateway(cosigner, HMACSigner(_KEY), log)

    with pytest.raises(RuntimeError):
        gw.submit_appeal(_make_record())
