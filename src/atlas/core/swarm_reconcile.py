"""
Capa 3 — Reconciliación enjambre → repo vivo (ADR-046, reconciliación "1 y 2").

Un artefacto ACEPTADO del blackboard (diff verificado por capa 1) se convierte
en una propuesta ColdUpdate. De ahí sigue el camino seguro existente: validate
→ seam del decider. **Auto-apply arranca APAGADO**: el reconciler solo PROPONE;
quién (y si) aplica lo decide el decider. Bajo HumanDecider espera aprobación;
bajo autónomo aplica solo lo reversible/bajo riesgo, ya con el validate +
rollback de ColdUpdate. Nada se auto-mergea aquí.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Protocol

from atlas.core.swarm import BlackboardEntry
from atlas.core.verify import Artifact


class _ColdUpdateLike(Protocol):
    def propose(
        self,
        intent: str,
        patch_path: Path,
        *,
        base_ref: str = ...,
        origin: str = ...,
        risk: str = ...,
        evidence: dict[str, Any] | None = ...,
    ) -> Any: ...


class ColdUpdateReconciler:
    """Hook `on_accepted` del SwarmCoordinator: artefacto aceptado → propuesta
    ColdUpdate. No aplica; deja la propuesta para el seam del decider."""

    def __init__(
        self,
        manager: _ColdUpdateLike,
        *,
        risk: str = "low",
        origin: str = "swarm",
    ) -> None:
        self._manager = manager
        self._risk = risk
        self._origin = origin
        self.proposed_ids: list[str] = []

    def __call__(self, entry: BlackboardEntry, artifact: Artifact) -> None:
        diff = str(artifact.payload.get("diff", ""))
        if not diff.strip():
            return  # nada que proponer (artefacto no-patch)
        # El patch se materializa en un fichero temporal; ColdUpdate lo copia a
        # su store. tempfile evita ensuciar el repo.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(diff)
            patch_path = Path(fh.name)
        try:
            proposal = self._manager.propose(
                f"[swarm:{entry.worker_id}] {entry.domain}",
                patch_path,
                origin=self._origin,
                risk=self._risk,
                evidence={
                    "swarm_entry_id": entry.id,
                    "worker_id": entry.worker_id,
                    "domain": entry.domain,
                    "verification": entry.evidence,
                },
            )
        finally:
            patch_path.unlink(missing_ok=True)
        self.proposed_ids.append(proposal.id)
