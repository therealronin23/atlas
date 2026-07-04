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
from typing import TYPE_CHECKING, Any, Callable

from atlas.core.git_env import clean_git_env
from atlas.core.validation_runner import ValidationReport, ValidationRunner
from atlas.logging.merkle_logger import MerkleLogger

if TYPE_CHECKING:
    from atlas.core.decider.decider import Decider


TIPO1_TRANSFORMS: frozenset[str] = frozenset({
    "strip_trailing_whitespace",
    "ensure_final_newline",
    "collapse_eof_blank_lines",
})


def _is_tipo1_diff(diff_text: str) -> bool:
    """True si TODOS los cambios del diff son whitespace-only (tipo-1 mecánico).

    Por cada hunk, empareja líneas '-' con '+' por posición. Una pareja es tipo-1
    si `old.rstrip() == new.rstrip()`. Líneas sin pareja (hunk desbalanceado) deben
    ser whitespace-only (blank line changes). Un diff vacío o sin hunks → False
    (fail-closed: no-ops no auto-aplican).
    """
    def _check_hunk(minus: list[str], plus: list[str]) -> bool:
        n = min(len(minus), len(plus))
        for i in range(n):
            if minus[i].rstrip() != plus[i].rstrip():
                return False
        for line in minus[n:] + plus[n:]:
            if line.rstrip():  # contenido no-whitespace sin pareja → no tipo-1
                return False
        return True

    in_hunk = False
    has_hunk = False
    minus_lines: list[str] = []
    plus_lines: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if in_hunk and not _check_hunk(minus_lines, plus_lines):
                return False
            minus_lines = []
            plus_lines = []
            in_hunk = True
            has_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("-"):
            minus_lines.append(line[1:])
        elif line.startswith("+"):
            plus_lines.append(line[1:])

    if in_hunk and not _check_hunk(minus_lines, plus_lines):
        return False
    return has_hunk


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
    forensics: dict[str, Any] = field(default_factory=dict)
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
        runner_factory: Callable[[Path], ValidationRunner] | None = None,
        decider: "Decider | None" = None,
        root_cause_classifier: Any | None = None,
    ) -> None:
        self._root = project_root.resolve()
        self._merkle = merkle
        self._store_dir = store_dir or (self._root.parent / "atlas-cold-updates")
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._proposals_file = self._store_dir / "proposals.json"
        self._proposals: dict[str, ColdUpdateProposal] = {}
        self._runner_factory = runner_factory or (lambda p: ValidationRunner(p))
        self._decider = decider
        # Opcional (paso 3 del roadmap "juicio real"): RootCauseClassifier.
        # Sin inyectar, validate() se comporta exactamente igual que antes.
        self._root_cause_classifier = root_cause_classifier
        self._load()

    def _load(self) -> None:
        if not self._proposals_file.exists():
            return
        try:
            data = json.loads(self._proposals_file.read_text(encoding="utf-8"))
            for item in data.get("proposals", []):
                item.setdefault("forensics", {})
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
        # El patch vive en el store root, NO dentro del worktree: así el
        # worktree se puede destruir en estado terminal sin perder el patch
        # que rollback_applied necesita.
        stored_patch = self._store_dir / f"patch-{proposal_id}.patch"
        shutil.copy2(patch_path, stored_patch)
        try:
            self._apply_patch(wt_dir, stored_patch)
        except Exception:
            # Worktree creado pero patch no aplicable: limpiar antes de propagar.
            _stub = ColdUpdateProposal(
                id=proposal_id,
                intent="",
                status="failed",
                worktree_path=str(wt_dir),
                patch_path=str(stored_patch),
                base_ref=base_ref,
            )
            self._remove_worktree(_stub)
            raise

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
        worktree = Path(proposal.worktree_path)
        runner = self._runner_factory(worktree)
        report = runner.run()

        if not report.passed:
            # Registrar forense del primer intento.
            first_forensics: dict[str, Any] = {
                "pytest_summary": report.pytest_summary[:2000],
                "mypy_summary": report.mypy_summary[:2000],
                "pytest_exit": report.pytest_exit,
                "mypy_exit": report.mypy_exit,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            # Flaky-suspect: pytest falla (exit!=0) y no hay cambios en tests/.
            # Si solo mypy falla (pytest_exit==0) no se reintenta.
            flaky_candidate = (
                report.pytest_exit != 0
                and self._tests_diff_empty(worktree, proposal.base_ref)
            )
            if flaky_candidate:
                first_forensics["flaky_suspect"] = True
                proposal.forensics = first_forensics
                retry_runner = self._runner_factory(worktree)
                retry_report = retry_runner.run()
                if retry_report.passed:
                    # Reintento exitoso → validated.
                    report = retry_report
                    proposal.forensics["retry"] = retry_report.to_dict()
                else:
                    # Reintento también falla → failed con forense de ambos.
                    proposal.forensics["retry"] = {
                        "pytest_summary": retry_report.pytest_summary[:2000],
                        "mypy_summary": retry_report.mypy_summary[:2000],
                        "pytest_exit": retry_report.pytest_exit,
                        "mypy_exit": retry_report.mypy_exit,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    report = retry_report
                    self._route_anomaly(proposal)
            else:
                proposal.forensics = first_forensics

            # Razonar el PORQUÉ del fallo final (paso 3): antes solo se
            # guardaba el texto crudo, nadie clasificaba si era ambiental o
            # causado de verdad por el diff — así se quedaron 38 propuestas
            # legítimas atascadas una semana por un motivo ajeno (YAML sin
            # commit). Señal, nunca gate: si falla, no afecta report.passed.
            if self._root_cause_classifier is not None:
                try:
                    verdict = self._root_cause_classifier.classify(
                        pytest_summary=report.pytest_summary,
                        mypy_summary=report.mypy_summary,
                        base_ref=proposal.base_ref,
                    )
                    proposal.forensics["root_cause"] = verdict.to_dict()
                except Exception:  # noqa: BLE001 — señal, no gate; nunca bloquea validate()
                    pass

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
        post = self._runner_factory(self._root).run()
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
            self._remove_worktree(proposal)
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
        self._commit_with_evidence(proposal, post)
        self._remove_worktree(proposal)
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
        self._remove_worktree(proposal)
        return True

    def tier1_auto_apply(self, proposal_id: str) -> dict[str, Any]:
        """Auto-aplica un patch tipo-1 (MECHANICAL) sin HITL.

        Invariantes G0.6 — todo falla-cerrado:
        1. proposal.origin == "swarm"
        2. Diff contiene SOLO cambios whitespace (_is_tipo1_diff)
        3. BwrapJail disponible en el sistema (sin jail → Deny)
        Pipeline: validate() → approve() → apply() sin intervención humana.
        """
        proposal = self._require(proposal_id)

        if proposal.origin != "swarm":
            raise ValueError(
                f"tier1_auto_apply solo para origin='swarm', recibido '{proposal.origin}'"
            )

        diff_text = Path(proposal.patch_path).read_text(encoding="utf-8")
        if not _is_tipo1_diff(diff_text):
            raise ValueError(
                "Diff contiene cambios no-whitespace — no es tipo-1. Requiere HITL."
            )

        # Invariante: BwrapJail disponible (fail-closed: sin jail → Deny)
        try:
            from atlas.security.bwrap_jail import BwrapJail
            BwrapJail()
        except Exception as exc:
            raise RuntimeError(
                f"BwrapJail no disponible; tipo-1 auto-apply denegado: {exc}"
            ) from exc

        # Pipeline sin HITL
        report = self.validate(proposal_id)
        if not report.passed:
            raise RuntimeError(
                f"Validación falló en tier1_auto_apply; denegado. "
                f"pytest={report.pytest_exit} mypy={report.mypy_exit}"
            )
        self.approve(proposal_id)
        result = self.apply(proposal_id)

        self._merkle.log(
            action="cold_update.tier1_auto_applied",
            agent="cold_update_manager",
            result="success",
            risk_level="low",
            payload={"proposal_id": proposal_id, "origin": proposal.origin},
        )
        return result

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
        self._remove_worktree(proposal)
        return proposal

    def review_summary(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._require(proposal_id)
        return {
            "proposal": proposal.to_dict(),
            "diff_stat": self._diff_stat(Path(proposal.worktree_path)),
        }

    def _route_anomaly(self, proposal: ColdUpdateProposal) -> None:
        """Enruta una anomalía SUSPECT_FLAKY persistente al decisor intercambiable.

        Llamado cuando un reintento de validación también falla en una propuesta
        marcada como flaky_suspect. Si no hay decisor configurado, no hace nada
        (retrocompat). Si hay decisor, construye la acción con la forense completa
        en el context y llama decide(). El veredicto queda registrado en
        ``proposal.forensics['anomaly_verdict']`` y en merkle.

        No fuerza ningún resultado: bajo HumanDecider → RequiresHuman (se
        surfacea la anomalía); bajo AutonomousDecider → decide por invariantes.
        """
        if self._decider is None:
            return

        from atlas.core.decider.decider import DecisionAction

        action = DecisionAction(
            kind="cold_update_anomaly",
            mutating=False,
            reversible=True,
            descriptor=proposal.id,
        )
        context: dict[str, object] = {
            "proposal_id": proposal.id,
            "intent": proposal.intent,
            "forensics": proposal.forensics,
        }
        verdict = self._decider.decide(action, proposal.intent, context)
        verdict_repr = repr(verdict)
        proposal.forensics["anomaly_verdict"] = verdict_repr
        self._merkle.log(
            action="cold_update.anomaly_routed",
            agent="cold_update_manager",
            result="routed",
            risk_level="moderate",
            payload={
                "proposal_id": proposal.id,
                "verdict": verdict_repr,
            },
        )

    def _validate_origin(self, origin: str) -> None:
        if origin not in {"manual", "self_audit", "swarm"}:
            raise ValueError("origin debe ser manual, self_audit o swarm")

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
            env=clean_git_env(),
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
                env=clean_git_env(),
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

    def _tests_diff_empty(self, worktree: Path, base_ref: str) -> bool:
        """True si ningún path bajo tests/ fue modificado/añadido respecto a base_ref.

        Comprueba tanto cambios rastreados (git diff) como ficheros nuevos no
        rastreados (git ls-files --others). Fail-closed: si cualquier subprocess
        falla devuelve False para NO asumir flaky.
        """
        if not worktree.exists():
            return False
        try:
            env = clean_git_env()
            # Cambios en ficheros ya rastreados.
            tracked = subprocess.run(
                ["git", "diff", "--name-only", base_ref, "--", "tests/"],
                cwd=worktree,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if tracked.returncode != 0:
                return False
            if tracked.stdout.strip():
                return False
            # Ficheros nuevos no rastreados bajo tests/.
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "--", "tests/"],
                cwd=worktree,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if untracked.returncode != 0:
                return False
            return untracked.stdout.strip() == ""
        except Exception:
            return False

    def _diff_stat(self, worktree: Path) -> str:
        if not worktree.exists():
            return ""  # worktree ya destruido (estado terminal)
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=worktree,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or result.stderr or "").strip()[:2000]

    def _is_git_repo(self) -> bool:
        """True si self._root es un repositorio git (comprueba .git o git rev-parse)."""
        if (self._root / ".git").exists():
            return True
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _commit_with_evidence(
        self,
        proposal: ColdUpdateProposal,
        report: ValidationReport,
    ) -> None:
        """Commit best-effort tras apply exitoso.

        Genera un commit con mensaje de evidencia (verdict, checks, origin,
        proposal_id). Si el root no es git o el commit falla, se registra el
        fallo en forensics y apply() sigue devolviendo status 'applied'.
        """
        if not self._is_git_repo():
            return

        intent_snippet = proposal.intent[:200]
        msg = (
            f"cold_update: apply {proposal.id}\n\n"
            f"verdict: passed\n"
            f"pytest_exit: {report.pytest_exit}\n"
            f"mypy_exit: {report.mypy_exit}\n"
            f"origin: {proposal.origin}\n"
            f"proposal_id: {proposal.id}\n"
            f"intent: {intent_snippet}\n"
        )
        env = clean_git_env()
        try:
            add = subprocess.run(
                ["git", "add", "-A"],
                cwd=self._root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if add.returncode != 0:
                raise RuntimeError(f"git add -A failed: {add.stderr[:500]}")
            commit = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self._root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if commit.returncode != 0:
                raise RuntimeError(f"git commit failed: {commit.stderr[:500]}")
        except Exception as exc:
            proposal.forensics["commit_error"] = str(exc)[:500]
            proposal.forensics["commit_timestamp"] = datetime.now(timezone.utc).isoformat()
            self._save()
            self._merkle.log(
                action="cold_update.commit_failed",
                agent="cold_update_manager",
                result="failure",
                risk_level="moderate",
                payload={"proposal_id": proposal.id, "error": str(exc)[:300]},
            )

    def _remove_worktree(self, proposal: ColdUpdateProposal) -> None:
        """Teardown del worktree tras estado terminal. Idempotente. El patch
        vive en el store root, así que rollback_applied sigue funcionando."""
        wt = Path(proposal.worktree_path)
        if not wt.exists():
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)],
            cwd=self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        # Fallback para worktrees por copytree (repo no-git) o metadata divergente.
        # Nunca toca el root.
        if wt.exists() and wt.resolve() != self._root.resolve():
            shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
