"""
Capa 3 — reconciliación enjambre → ColdUpdate. Manager fake (no toca git ni
store real): se verifica que un artefacto aceptado PROPONE (no aplica) y que el
rechazado no propone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from atlas.core.swarm import Blackboard, Envelope, SwarmCoordinator
from atlas.core.swarm_reconcile import ColdUpdateReconciler
from atlas.core.verify import (
    Artifact,
    ArtifactKind,
    Check,
    CostTier,
    Evidence,
    UniversalVerifier,
    UnifiedDiffVerifier,
    Verdict,
)


class FakeColdUpdate:
    def __init__(self) -> None:
        self.proposals: list[dict[str, Any]] = []
        self.applied = 0

    def propose(self, intent, patch_path, *, base_ref="HEAD", origin="manual",
                risk="medium", evidence=None):  # noqa: ANN001
        self.proposals.append({
            "intent": intent,
            "patch": Path(patch_path).read_text(encoding="utf-8"),
            "origin": origin,
            "risk": risk,
            "evidence": evidence or {},
        })
        return SimpleNamespace(id=f"cold-{len(self.proposals)}")

    # Deliberadamente SIN apply automático: el reconciler nunca debe llamarlo.


_DIFF = "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def _diff_worker(worker_id: str, diff: str, code_domain: str = "maint"):
    class W:
        def __init__(self) -> None:
            self.worker_id = worker_id
            self.domain = code_domain
            self.produced: list = []

        def produce(self, task: Any) -> Artifact:
            self.produced.append(task)
            return Artifact(
                kind=ArtifactKind.PATCH,
                payload={"diff": diff},
                producer_cost=CostTier.SUITE,
                metadata={"allowed_paths": ["demo.py"]},
            )

    return W()


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _coord(reconciler) -> SwarmCoordinator:
    return SwarmCoordinator(
        UniversalVerifier([UnifiedDiffVerifier()]), Blackboard(), on_accepted=reconciler
    )


def test_accepted_artifact_becomes_proposal_not_applied() -> None:
    cold = FakeColdUpdate()
    reconciler = ColdUpdateReconciler(cold, risk="low")
    coord = _coord(reconciler)
    worker = _diff_worker("w1", _DIFF)
    coord.assign(worker, Envelope("w1", "maint", 100, _future()))

    result = coord.run_round({"w1": "sube x"})

    assert len(result.accepted) == 1
    assert len(cold.proposals) == 1  # propuesto
    assert cold.applied == 0          # NUNCA aplicado (auto-apply off)
    p = cold.proposals[0]
    assert p["origin"] == "swarm"
    assert p["risk"] == "low"
    assert p["patch"] == _DIFF
    assert p["evidence"]["worker_id"] == "w1"
    assert reconciler.proposed_ids == ["cold-1"]


def test_rejected_artifact_does_not_propose() -> None:
    cold = FakeColdUpdate()
    coord = _coord(ColdUpdateReconciler(cold))
    # diff fuera de allowed_paths → UnifiedDiffVerifier lo rechaza
    evil = "--- a/secrets.py\n+++ b/secrets.py\n@@ -1 +1 @@\n-a\n+b\n"
    coord.assign(_diff_worker("w1", evil), Envelope("w1", "maint", 100, _future()))

    result = coord.run_round({"w1": "t"})

    assert len(result.rejected) == 1
    assert cold.proposals == []  # nada propuesto desde un rechazo


def test_non_patch_artifact_is_skipped() -> None:
    cold = FakeColdUpdate()
    reconciler = ColdUpdateReconciler(cold)
    entry = SimpleNamespace(id="e1", worker_id="w1", domain="maint", evidence={})
    artifact = Artifact(kind=ArtifactKind.CODE, payload={"code": "x"}, producer_cost=CostTier.MODEL)
    reconciler(entry, artifact)  # sin 'diff' en payload
    assert cold.proposals == []


def test_reconciler_with_real_coldupdate(tmp_path: Path) -> None:
    """Integración con ColdUpdateManager real (store tmp, no-git → copytree)."""
    from atlas.core.cold_update_manager import ColdUpdateManager
    from atlas.logging.merkle_logger import MerkleLogger

    project = tmp_path / "proj"
    (project / "src" / "atlas").mkdir(parents=True)
    (project / "demo.py").write_text("x = 1\n", encoding="utf-8")
    merkle = MerkleLogger(tmp_path / "atlas" / "memory" / "audit")
    manager = ColdUpdateManager(project, merkle, store_dir=tmp_path / "store")

    reconciler = ColdUpdateReconciler(manager, risk="low")
    # nuevo fichero (aplicable por patch -p1 sobre copytree)
    diff = "--- /dev/null\n+++ b/src/atlas/new.txt\n@@ -0,0 +1 @@\n+swarm\n"
    entry = SimpleNamespace(id="e1", worker_id="w1", domain="maint", evidence={"v": 1})
    artifact = Artifact(kind=ArtifactKind.PATCH, payload={"diff": diff}, producer_cost=CostTier.SUITE)

    reconciler(entry, artifact)

    assert len(reconciler.proposed_ids) == 1
    proposal = manager.get(reconciler.proposed_ids[0])
    assert proposal is not None
    assert proposal.origin == "swarm"
    assert proposal.status == "proposed"  # propuesto, no aplicado
