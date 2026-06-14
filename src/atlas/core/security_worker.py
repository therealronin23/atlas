"""Backend de capa 3 para workers de seguridad (ADR-043/046).

SecurityWorker conforma el mismo contrato que WorktreeWorker (worker_id,
domain, produce) pero opera sobre SecurityFinding + AuthorizationGrant en
lugar de diffs de código. No escribe Merkle, no toca ATLAS_HOME.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from atlas.core.verify import Artifact, ArtifactKind, CostTier
from atlas.security.authorization import (
    AuthorizationGrant,
    AuthorizationVerifier,
    PoCReproductionVerifier,
    SecurityFinding,
)


@dataclass(frozen=True)
class SecurityTask:
    finding: SecurityFinding
    grant: AuthorizationGrant


class SecurityWorker:
    def __init__(
        self,
        worker_id: str,
        auth_verifier: AuthorizationVerifier,
        sandbox_factory: Callable[[], Any],
    ) -> None:
        self._worker_id = worker_id
        self._verifier = PoCReproductionVerifier(auth_verifier, sandbox_factory)

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def domain(self) -> str:
        return "security"

    def produce(self, task: SecurityTask) -> Artifact:
        evidence = self._verifier.verify(task.finding, task.grant)
        return Artifact(
            kind=ArtifactKind.SECURITY_FINDING_RESULT,
            payload={
                "evidence": evidence.to_dict(),
                "finding_id": task.finding.id,
            },
            producer_cost=evidence.total_cost,
            metadata={
                "worker_id": self._worker_id,
                "domain": "security",
                "target": task.finding.target,
                "capability": task.finding.capability.value,
            },
        )
