"""
ADR-048 fase F — Integración scout→VerifiedProducer→worker. Cableado end-to-end
sin git, sin red: el arnés determinista produce y el UnifiedDiffVerifier juzga.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.maintenance_scout import RepoMaintenanceScout
from atlas.core.maintenance_worker import (
    build_maintenance_producer,
    maintenance_produce_diff,
)
from atlas.core.verify import Artifact, ArtifactKind, CostTier
from atlas.router.cascade import Difficulty, TaskSpec


def test_deterministic_only_loop_verifies_diff() -> None:
    vp = build_maintenance_producer()
    [task] = RepoMaintenanceScout().scan([("a.py", "x = 1   \n")])
    out = vp.produce(task.to_spec())
    assert out.verified
    assert out.attempts[0].producer_id == "deterministic"


def test_clean_file_does_not_verify() -> None:
    # Fichero limpio → diff vacío → UnifiedDiffVerifier FALLA (sin hunks).
    vp = build_maintenance_producer()
    spec = TaskSpec(
        intent="nada que arreglar",
        kind=ArtifactKind.PATCH,
        metadata={"target_path": "a.py", "source": "x = 1\n"},
    )
    assert not vp.produce(spec).verified


def test_produce_diff_adapter_returns_string() -> None:
    vp = build_maintenance_producer()
    [task] = RepoMaintenanceScout().scan([("a.py", "x = 1   \n")])
    diff = maintenance_produce_diff(vp)(task, Path("/tmp/ignored"))
    assert diff.startswith("--- a/a.py")
    assert "@@" in diff


def test_produce_diff_adapter_empty_on_failure() -> None:
    vp = build_maintenance_producer()
    # Tarea sobre un fuente ya limpio: el arnés no produce diff → fallo honesto.
    from atlas.core.maintenance_scout import MaintenanceTask

    clean_task = MaintenanceTask("a.py", "strip_trailing_whitespace", "x = 1\n")
    assert maintenance_produce_diff(vp)(clean_task, Path("/tmp/x")) == ""


class _FakeLLM:
    producer_id = "inference:l1"
    cost = CostTier.MODEL
    capability = Difficulty.HARD

    def produce(self, spec: TaskSpec) -> Artifact:
        return Artifact(
            kind=ArtifactKind.PATCH,
            payload={"diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"},
            producer_cost=self.cost,
            metadata={"allowed_paths": ["a.py"]},
        )


def test_llm_escalation_when_deterministic_cannot_help() -> None:
    # Tarea HARD: el arnés (MECHANICAL) no es elegible → escala al LLM.
    vp = build_maintenance_producer(llm=_FakeLLM())
    spec = TaskSpec(
        intent="refactor de arquitectura",  # HARD por el estimador
        kind=ArtifactKind.PATCH,
        metadata={"target_path": "a.py", "source": "x = 1\n", "allowed_paths": ["a.py"]},
    )
    out = vp.produce(spec)
    assert out.verified
    assert out.attempts[-1].producer_id == "llm:inference:l1"
