"""
Capa 3 — Enjambre sobre blackboard. Workers fake, sin worktrees ni procesos
reales. Reusa el verificador de capa 1 y la CostLedger de capa 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from atlas.core.swarm import (
    Blackboard,
    EntryStatus,
    Envelope,
    SwarmCoordinator,
    Worker,
)
from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    UniversalVerifier,
    Verdict,
)
from atlas.logging.merkle_logger import MerkleLogger


@dataclass
class FakeChainVerifier:
    verifier_id: str
    cost: CostTier
    passing_codes: set[str]

    def applies_to(self, artifact: Artifact) -> bool:
        return "code" in artifact.payload

    def verify(self, artifact: Artifact) -> Evidence:
        ok = artifact.payload["code"] in self.passing_codes
        return Evidence(
            verdict=Verdict.PASS if ok else Verdict.FAIL,
            checks=(Check(name=self.verifier_id, passed=ok, cost=self.cost),),
            total_cost=self.cost,
            verifier_ids=(self.verifier_id,),
        )


@dataclass
class FakeWorker:
    worker_id: str
    domain: str
    code: str = "ok"
    produced: list[Any] = field(default_factory=list)

    def produce(self, task: Any) -> Artifact:
        self.produced.append(task)
        return Artifact(
            kind=ArtifactKind.CODE, payload={"code": self.code}, producer_cost=CostTier.MODEL
        )


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _verifier(passing: set[str]) -> UniversalVerifier:
    return UniversalVerifier([FakeChainVerifier("chk", CostTier.STATIC, passing)])


class TestEnvelope:
    def test_expiry(self) -> None:
        assert Envelope("w", "d", 10, _past()).is_expired()
        assert not Envelope("w", "d", 10, _future()).is_expired()

    def test_invalid_date_is_expired_fail_closed(self) -> None:
        assert Envelope("w", "d", 10, "no-es-fecha").is_expired()


class TestBlackboardLaw:
    def test_pass_accepted_fail_rejected_both_recorded(self) -> None:
        bb = Blackboard()
        good = Artifact(kind=ArtifactKind.CODE, payload={"code": "ok"}, producer_cost=CostTier.MODEL)
        bad = Artifact(kind=ArtifactKind.CODE, payload={"code": "no"}, producer_cost=CostTier.MODEL)
        verifier = _verifier({"ok"})

        e1 = bb.submit(worker_id="w", domain="d", artifact=good, evidence=verifier.verify(good))
        e2 = bb.submit(worker_id="w", domain="d", artifact=bad, evidence=verifier.verify(bad))
        assert e1.status is EntryStatus.ACCEPTED
        assert e2.status is EntryStatus.REJECTED
        assert len(bb.all()) == 2  # ambos quedan en el rastro
        assert len(bb.accepted()) == 1 and len(bb.rejected()) == 1

    def test_submit_logs_to_merkle(self, tmp_path) -> None:
        merkle = MerkleLogger(tmp_path / "merkle")
        bb = Blackboard(merkle=merkle)
        art = Artifact(kind=ArtifactKind.CODE, payload={"code": "ok"}, producer_cost=CostTier.MODEL)
        bb.submit(worker_id="w", domain="d", artifact=art, evidence=_verifier({"ok"}).verify(art))
        assert "blackboard.submit" in [r.to_dict()["action"] for r in merkle.tail(5)]


class TestCoordinatorRounds:
    def test_accepted_artifact_lands(self) -> None:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        worker = FakeWorker("w1", "maint", code="ok")
        coord.assign(worker, Envelope("w1", "maint", budget_units=100, expires_at=_future()))
        result = coord.run_round({"w1": "tarea"})
        assert len(result.accepted) == 1
        assert result.accepted[0].worker_id == "w1"
        assert coord.ledger.verified_count == 1

    def test_rejected_artifact_does_not_count_verified(self) -> None:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        coord.assign(FakeWorker("w1", "maint", code="basura"),
                     Envelope("w1", "maint", 100, _future()))
        result = coord.run_round({"w1": "t"})
        assert len(result.rejected) == 1
        assert coord.ledger.verified_count == 0

    def test_expired_envelope_skips_worker(self) -> None:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        worker = FakeWorker("w1", "maint")
        coord.assign(worker, Envelope("w1", "maint", 100, _past()))
        result = coord.run_round({"w1": "t"})
        assert result.skipped == ("w1",)
        assert worker.produced == []  # ni se le pide producir

    def test_budget_exhaustion_stops_worker(self) -> None:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        worker = FakeWorker("w1", "maint", code="ok")
        # MODEL(5)+STATIC(1)=6 por intento; budget 6 alcanza para UNO solo.
        coord.assign(worker, Envelope("w1", "maint", budget_units=6, expires_at=_future()))
        r1 = coord.run_round({"w1": "t"})
        r2 = coord.run_round({"w1": "t"})
        assert len(r1.accepted) == 1
        assert r2.skipped == ("w1",)
        assert coord.remaining_budget("w1") == 0

    def test_unassigned_worker_skipped(self) -> None:
        coord = SwarmCoordinator(_verifier({"ok"}), Blackboard())
        assert coord.run_round({"ghost": "t"}).skipped == ("ghost",)

    def test_assign_rejects_mismatched_envelope(self) -> None:
        coord = SwarmCoordinator(_verifier({"ok"}), Blackboard())
        with pytest.raises(ValueError, match="asignado a worker"):
            coord.assign(FakeWorker("w1", "maint"), Envelope("OTRO", "maint", 10, _future()))

    def test_multiple_workers_one_round(self) -> None:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        coord.assign(FakeWorker("w1", "maint", code="ok"), Envelope("w1", "maint", 100, _future()))
        coord.assign(FakeWorker("w2", "maint", code="no"), Envelope("w2", "maint", 100, _future()))
        coord.assign(FakeWorker("w3", "maint", code="ok"), Envelope("w3", "maint", 100, _future()))
        result = coord.run_round({"w1": "t", "w2": "t", "w3": "t"})
        assert len(result.accepted) == 2
        assert len(result.rejected) == 1

    def test_on_accepted_hook_failure_does_not_kill_round(self) -> None:
        bb = Blackboard()

        def failing_hook(entry, artifact):
            raise RuntimeError("boom")

        coord = SwarmCoordinator(_verifier({"ok"}), bb, on_accepted=failing_hook)
        worker = FakeWorker("w1", "maint", code="ok")
        coord.assign(worker, Envelope("w1", "maint", 100, _future()))

        result = coord.run_round({"w1": "t"})

        # El entry fue aceptado a pesar del fallo del hook
        assert len(result.accepted) == 1
        assert result.accepted[0].status is EntryStatus.ACCEPTED
        # El error se capturó sin propagarse
        assert len(result.reconcile_errors) == 1
        assert result.reconcile_errors[0][0] == result.accepted[0].id
        assert "boom" in result.reconcile_errors[0][1]


class TestAuditSampling:
    def _coord_with_n_accepted(self, n: int) -> SwarmCoordinator:
        bb = Blackboard()
        coord = SwarmCoordinator(_verifier({"ok"}), bb)
        for i in range(n):
            wid = f"w{i}"
            coord.assign(FakeWorker(wid, "maint", code="ok"),
                         Envelope(wid, "maint", 100, _future()))
        coord.run_round({f"w{i}": "t" for i in range(n)})
        return coord

    def test_sample_fraction_is_deterministic(self) -> None:
        coord = self._coord_with_n_accepted(10)
        s1 = coord.audit_sample(0.3, rng_seed=42)
        s2 = coord.audit_sample(0.3, rng_seed=42)
        assert len(s1) == 3
        assert [e.id for e in s1] == [e.id for e in s2]

    def test_sample_zero_and_full(self) -> None:
        coord = self._coord_with_n_accepted(5)
        assert coord.audit_sample(0) == []
        assert len(coord.audit_sample(1.0)) == 5

    def test_sample_rounds_up_to_at_least_one(self) -> None:
        coord = self._coord_with_n_accepted(4)
        assert len(coord.audit_sample(0.01)) == 1


class TestLayerComposition:
    """El enjambre reusa capa 1 (verificación) y capa 2 (CostLedger) sin
    maquinaria nueva: la ley del blackboard es la Evidence PASS."""

    def test_cost_per_verified_result_flows_from_ledger(self) -> None:
        coord = SwarmCoordinator(_verifier({"ok"}), Blackboard())
        coord.assign(FakeWorker("w1", "maint", code="ok"), Envelope("w1", "maint", 100, _future()))
        coord.run_round({"w1": "t"})
        # MODEL(5)+STATIC(1)=6, un resultado verificado
        assert coord.ledger.cost_per_verified_result() == 6.0
