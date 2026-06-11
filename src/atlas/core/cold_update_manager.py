"""
ADR-025 — ColdUpdateManager: isolated worktree, patch intake, validation, HITL apply.
No hot self-patch; no autonomous code generation in MVP.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.validation_runner import ValidationReport, ValidationRunner
from atlas.logging.merkle_logger import MerkleLogger


@dataclass
class ColdUpdateProposal:
    id: str
    intent: str
    status: str  # proposed | validated | approved | applied | rejected | failed | rolled_back
    worktree_path: str
    patch_path: str
    base_ref: str
    origin: str = "manual"  # manual | self_audit
    risk: str = "medium"    # low | medium | high | critical
    evidence: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ColdUpdateManager:
    """MVP: accept patch, worktree, validate, await approval, apply with rollback guard."""

    ALLOWED_PREFIXES = ("src/", "tests/", "scripts/", "docs/", "config/")

    def __init__(
        self,
        project_root: Path,
        merkle: MerkleLogger,
        store_dir: Path | None = None,
    ) -> None:
        self._root = project_root.resolve()
        self._merkle = merkle
        self._store_dir = store_dir or (self._root.parent / "atlas-cold-updates")
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._proposals_file = self._store_dir / "proposals.json"
        self._proposals: dict[str, ColdUpdateProposal] = {}
        self._load()

    def _load(self) -> None:
        if not self._proposals_file.exists():
            return
        try:
            data = json.loads(self._proposals_file.read_text(encoding="utf-8"))
            for item in data.get("proposals", []):
                p = ColdUpdateProposal(**item)
                self._proposals[p.id] = p
        except Exception:
            pass

    def _save(self) -> None:
        payload = {"proposals": [p.to_dict() for p in self._proposals.values()]}
        self._proposals_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_proposals(self) -> list[ColdUpdateProposal]:
        return sorted(self._proposals.values(), key=lambda p: p.created_at, reverse=True)

    def get(self, proposal_id: str) -> ColdUpdateProposal | None:
        return self._proposals.get(proposal_id)

    def propose(
        self,
        intent: str,
        patch_path: Path,
        *,
        base_ref: str = "HEAD",
        origin: str = "manual",
        risk: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> ColdUpdateProposal:
        patch_path = patch_path.resolve()
        if not patch_path.is_file():
            raise FileNotFoundError(f"Patch no encontrado: {patch_path}")
        self._validate_origin(origin)
        self._validate_risk(risk)

        proposal_id = str(uuid.uuid4())[:12]
        wt_dir = self._store_dir / f"worktree-{proposal_id}"
        if wt_dir.exists():
            shutil.rmtree(wt_dir)

        self._create_worktree(wt_dir, base_ref)
        stored_patch = wt_dir / "proposal.patch"
        shutil.copy2(patch_path, stored_patch)
        self._apply_patch(wt_dir, stored_patch)

        proposal = ColdUpdateProposal(
            id=proposal_id,
            intent=intent,
            status="proposed",
            worktree_path=str(wt_dir),
            patch_path=str(stored_patch),
            base_ref=base_ref,
            origin=origin,
            risk=risk,
            evidence=evidence or {},
        )
        self._proposals[proposal_id] = proposal
        self._save()
        self._merkle.log(
            action="cold_update.proposed",
            agent="cold_update_manager",
            result="success",
            risk_level="high",
            payload={
                "proposal_id": proposal_id,
                "intent": intent[:200],
                "origin": origin,
                "risk": risk,
            },
        )
        return proposal

    def attach_evidence(
        self,
        proposal_id: str,
        evidence: dict[str, Any],
    ) -> ColdUpdateProposal:
        proposal = self._require(proposal_id)
        proposal.evidence.update(evidence)
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.evidence_attached",
            agent="cold_update_manager",
            result="success",
            risk_level="moderate",
            payload={
                "proposal_id": proposal_id,
                "keys": sorted(evidence.keys()),
            },
        )
        return proposal

    def validate(self, proposal_id: str) -> ValidationReport:
        proposal = self._require(proposal_id)
        runner = ValidationRunner(Path(proposal.worktree_path))
        report = runner.run()
        proposal.validation = report.to_dict()
        proposal.status = "validated" if report.passed else "failed"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.validated",
            agent="cold_update_manager",
            result="success" if report.passed else "failure",
            risk_level="high",
            payload={
                "proposal_id": proposal_id,
                "passed": report.passed,
                "pytest_exit": report.pytest_exit,
                "mypy_exit": report.mypy_exit,
            },
        )
        return report

    def approve(self, proposal_id: str) -> ColdUpdateProposal:
        proposal = self._require(proposal_id)
        if proposal.status != "validated":
            raise RuntimeError(
                f"Requiere validacion previa (estado={proposal.status}). "
                "Ejecuta: atlas update validate <id>"
            )
        if not proposal.validation or not proposal.validation.get("passed"):
            raise RuntimeError("Validacion fallida; no se puede aprobar")
        proposal.status = "approved"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.approved",
            agent="cold_update_manager",
            result="success",
            risk_level="critical",
            payload={"proposal_id": proposal_id},
        )
        return proposal

    def apply(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._require(proposal_id)
        if proposal.status != "approved":
            raise RuntimeError("Requiere aprobacion explicita antes de apply")

        patch = Path(proposal.patch_path)
        self._apply_patch(self._root, patch)
        post = ValidationRunner(self._root).run()
        if not post.passed:
            self._rollback_patch(self._root, patch)
            proposal.status = "failed"
            self._save()
            self._merkle.log(
                action="cold_update.rollback",
                agent="cold_update_manager",
                result="failure",
                risk_level="critical",
                payload={"proposal_id": proposal_id, "reason": "post_apply_checks_failed"},
            )
            raise RuntimeError("Post-apply validation failed; patch reverted")

        proposal.status = "applied"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.applied",
            agent="cold_update_manager",
            result="success",
            risk_level="critical",
            payload={"proposal_id": proposal_id},
        )
        return {"proposal_id": proposal_id, "status": "applied", "validation": post.to_dict()}

    def rollback_applied(self, proposal_id: str) -> bool:
        """Deshace un patch ya aplicado (primitiva de undo para el seam ADR-040).

        Reverse-apply del patch sobre el root y estado ``rolled_back``. Solo
        aplica a propuestas en estado ``applied``; idempotente sobre el resto
        (devuelve False sin tocar nada)."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != "applied":
            return False
        self._rollback_patch(self._root, Path(proposal.patch_path))
        proposal.status = "rolled_back"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.rolled_back",
            agent="cold_update_manager",
            result="success",
            risk_level="critical",
            payload={"proposal_id": proposal_id},
        )
        return True

    def reject(self, proposal_id: str, reason: str = "") -> ColdUpdateProposal:
        proposal = self._require(proposal_id)
        proposal.status = "rejected"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._merkle.log(
            action="cold_update.rejected",
            agent="cold_update_manager",
            result="blocked",
            risk_level="moderate",
            payload={"proposal_id": proposal_id, "reason": reason[:500]},
        )
        return proposal

    def review_summary(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._require(proposal_id)
        return {
            "proposal": proposal.to_dict(),
            "diff_stat": self._diff_stat(Path(proposal.worktree_path)),
        }

    def _validate_origin(self, origin: str) -> None:
        if origin not in {"manual", "self_audit"}:
            raise ValueError("origin debe ser manual o self_audit")

    def _validate_risk(self, risk: str) -> None:
        if risk not in {"low", "medium", "high", "critical"}:
            raise ValueError("risk debe ser low, medium, high o critical")

    def _require(self, proposal_id: str) -> ColdUpdateProposal:
        p = self._proposals.get(proposal_id)
        if p is None:
            raise KeyError(f"Proposal no encontrado: {proposal_id}")
        return p

    def _create_worktree(self, path: Path, base_ref: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), base_ref],
            cwd=self._root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            # Fallback: copy tree for non-git or worktree failure (tests)
            if (self._root / ".git").exists():
                raise RuntimeError(f"git worktree add failed: {result.stderr}")
            shutil.copytree(
                self._root,
                path,
                ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git", "atlas-cold-updates"),
                dirs_exist_ok=True,
            )

    def _apply_patch(self, target: Path, patch: Path) -> None:
        last_err = ""
        for cmd in (
            ["git", "apply", str(patch)],
            ["patch", "-p1", "-i", str(patch)],
        ):
            result = subprocess.run(
                cmd,
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return
            last_err = result.stderr or result.stdout or ""
        raise RuntimeError(f"Patch no aplicable: {last_err[:500]}")

    def _rollback_patch(self, target: Path, patch: Path) -> None:
        subprocess.run(
            ["patch", "-p1", "-R", "-i", str(patch)],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )

    def _diff_stat(self, worktree: Path) -> str:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or result.stderr or "").strip()[:2000]
