"""
ADR-048 — swarm_audit: re-verifica propuestas swarm aceptadas por el verificador
barato usando la suite completa en un ATLAS_HOME aislado.

Detecta puntos ciegos del UnifiedDiffVerifier: propuestas que pasaron el gate
barato pero fallan la suite real.
"""

from __future__ import annotations

import random
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from atlas.core.validation_runner import ValidationReport, ValidationRunner


def _default_runner(worktree: Path, atlas_home: Path) -> ValidationRunner:
    return ValidationRunner(
        worktree,
        extra_env={
            "ATLAS_HOME": str(atlas_home),
            "ATLAS_MEMORY_VECTOR": "0",
        },
    )


def reverify_swarm_proposals(
    manager: Any,
    *,
    fraction: float,
    merkle: Any,
    rng_seed: int = 0,
    atlas_home: Path | None = None,
    runner_factory: Callable[[Path, Path], Any] | None = None,
) -> dict:
    """Re-ejecuta la suite completa sobre una muestra de propuestas swarm.

    Propuestas origin="swarm" con status proposed/validated ya pasaron el
    verificador barato (UnifiedDiffVerifier). Si la suite las rechaza, eso es
    un punto ciego del verificador barato → divergencia.

    El ATLAS_HOME usado es aislado (tmp) para no contaminar el workspace vivo.
    """
    empty: dict = {
        "sampled": 0,
        "reverified": 0,
        "divergences": 0,
        "records": [],
    }

    props = [
        p
        for p in manager.list_proposals()
        if getattr(p, "origin", "") == "swarm"
        and p.status in {"proposed", "validated"}
    ]
    if not props or fraction <= 0:
        return empty

    # Muestra determinista
    rng = random.Random(rng_seed)
    if fraction >= 1:
        k = len(props)
        sample = props
    else:
        k = max(1, round(len(props) * fraction))
        sample = rng.sample(props, k)

    # ATLAS_HOME aislado
    created_home = atlas_home is None
    home: Path
    if atlas_home is None:
        home = Path(tempfile.mkdtemp(prefix="atlas-audit-sample-"))
    else:
        home = atlas_home

    records: list[dict] = []
    factory = runner_factory or _default_runner

    try:
        for p in sample:
            wt_path = getattr(p, "worktree_path", None)
            evidence = getattr(p, "evidence", {}) or {}
            base: dict = {
                "proposal_id": p.id,
                "signature": evidence.get("signature"),
                "cheap_verdict": "pass",
            }

            if not wt_path or not Path(wt_path).exists():
                records.append({**base, "suite_passed": None, "skipped": "worktree_ausente"})
                continue

            runner = factory(Path(wt_path), home)
            report: ValidationReport = runner.run()
            records.append(
                {
                    **base,
                    "suite_passed": report.passed,
                    "pytest_exit": report.pytest_exit,
                    "mypy_exit": report.mypy_exit,
                }
            )
    finally:
        if created_home:
            shutil.rmtree(home, ignore_errors=True)

    divergences = [r for r in records if r.get("suite_passed") is False]
    reverified = sum(1 for r in records if r.get("suite_passed") is not None)

    merkle.log(
        action="swarm.audit_sample",
        agent="swarm_audit",
        result="success" if not divergences else "blocked",
        risk_level="moderate",
        payload={
            "sampled": len(sample),
            "reverified": reverified,
            "divergences": len(divergences),
            "divergent_ids": [r["proposal_id"] for r in divergences],
        },
    )

    return {
        "sampled": len(sample),
        "reverified": reverified,
        "divergences": len(divergences),
        "records": records,
        "divergent_ids": [r["proposal_id"] for r in divergences],
    }
