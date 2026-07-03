"""
ColdUpdateBatcher — combina propuestas `validated` con el mismo `origin` en
un unico lote, prueba el lote combinado en un worktree temporal y, si falla,
biseca para excluir a la propuesta (o propuestas) culpable(s).

No aplica nada a la rama real: solo prueba en worktrees efimeros y persiste
el resultado (`batches.json`). La aplicacion real sigue pasando por el flujo
existente de ColdUpdateManager (propose/validate/approve/apply), fuera del
alcance de este componente.
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
from atlas.core.validation_runner import ValidationRunner

if TYPE_CHECKING:
    from atlas.core.cold_update_manager import ColdUpdateManager
    from atlas.logging.merkle_logger import MerkleLogger


@dataclass
class BatchResult:
    id: str
    included: list[str]
    excluded: list[dict[str, Any]]
    passed: bool
    pytest_summary: str
    mypy_summary: str
    worktree_path: str | None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Señal adicional (paso 2 del roadmap "juicio real"), NUNCA un gate duro:
    # no bloquea el lote, solo se persiste para que la revisión humana la vea.
    premortem: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ColdUpdateBatcher:
    """Agrega propuestas `validated` de un mismo origen en un lote probado
    conjuntamente, con bisección simple ante fallo."""

    def __init__(
        self,
        manager: "ColdUpdateManager",
        *,
        store_dir: Path | None = None,
        runner_factory: Callable[[Path], ValidationRunner] | None = None,
        merkle: "MerkleLogger | None" = None,
        premortem: Any | None = None,
    ) -> None:
        self._manager = manager
        self._root = manager._root
        self._store_dir = store_dir or manager._store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._batches_file = self._store_dir / "batches.json"
        self._runner_factory = runner_factory or (lambda p: ValidationRunner(p))
        self._merkle = merkle or manager._merkle
        # Opcional (paso 2 del roadmap "juicio real"): BatchPremortemGate.
        # Si no se inyecta, run_batch() se comporta exactamente igual que antes.
        self._premortem = premortem

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def run_batch(self, *, origin: str = "self_audit", base_ref: str = "HEAD") -> BatchResult:
        candidates = [
            p for p in self._manager.list_proposals()
            if p.status == "validated" and p.origin == origin
        ]
        # Orden estable: por created_at ascendente (orden de aparición).
        candidates.sort(key=lambda p: p.created_at)

        if not candidates:
            return self._finalize(
                included=[], excluded=[], passed=True,
                pytest_summary="", mypy_summary="",
            )

        # Paso 2 del roadmap "juicio real" (corrección del Cónclave: razonar
        # sobre el riesgo de la COMBINACIÓN antes de pagar el coste de correr
        # la suite completa). Señal adicional, nunca bloquea: si el premortem
        # falla o no está inyectado, el lote sigue su camino normal igual.
        premortem_findings: dict[str, Any] | None = None
        if self._premortem is not None:
            try:
                premortem_findings = self._premortem.assess(candidates).to_dict()
            except Exception:  # noqa: BLE001 — señal, no gate; nunca bloquea el lote
                premortem_findings = None

        combined_wt = self._new_worktree_path()
        try:
            self._create_worktree(combined_wt, base_ref)
            for proposal in candidates:
                self._apply_patch(combined_wt, Path(proposal.patch_path))
            report = self._runner_factory(combined_wt).run()
        finally:
            self._remove_worktree(combined_wt)

        if report.passed:
            return self._finalize(
                included=[p.id for p in candidates],
                excluded=[],
                passed=True,
                pytest_summary=report.pytest_summary,
                mypy_summary=report.mypy_summary,
                premortem_findings=premortem_findings,
            )

        return self._bisect(candidates, base_ref, premortem_findings=premortem_findings)

    def get_batch(self, batch_id: str) -> BatchResult | None:
        for item in self._load()["batches"]:
            if item.get("id") == batch_id:
                return BatchResult(**item)
        return None

    def latest_batch(self) -> BatchResult | None:
        batches = self._load()["batches"]
        if not batches:
            return None
        latest = max(batches, key=lambda b: b.get("created_at", ""))
        return BatchResult(**latest)

    # ------------------------------------------------------------------
    # Bisección
    # ------------------------------------------------------------------

    def _bisect(
        self,
        candidates: list[Any],
        base_ref: str,
        *,
        premortem_findings: dict[str, Any] | None = None,
    ) -> BatchResult:
        confirmed_good: list[Any] = []
        excluded: list[dict[str, Any]] = []

        for candidate in candidates:
            trial = [*confirmed_good, candidate]
            wt = self._new_worktree_path()
            try:
                self._create_worktree(wt, base_ref)
                for proposal in trial:
                    self._apply_patch(wt, Path(proposal.patch_path))
                report = self._runner_factory(wt).run()
            finally:
                self._remove_worktree(wt)

            if report.passed:
                confirmed_good.append(candidate)
            else:
                excluded.append({
                    "proposal_id": candidate.id,
                    "reason": f"rompe la suite combinada (pytest_exit={report.pytest_exit})",
                })

        if not confirmed_good:
            return self._finalize(
                included=[],
                excluded=excluded,
                passed=False,
                pytest_summary="",
                mypy_summary="",
                premortem_findings=premortem_findings,
            )

        final_wt = self._new_worktree_path()
        try:
            self._create_worktree(final_wt, base_ref)
            for proposal in confirmed_good:
                self._apply_patch(final_wt, Path(proposal.patch_path))
            final_report = self._runner_factory(final_wt).run()
        finally:
            self._remove_worktree(final_wt)

        return self._finalize(
            included=[p.id for p in confirmed_good],
            excluded=excluded,
            passed=final_report.passed,
            pytest_summary=final_report.pytest_summary,
            mypy_summary=final_report.mypy_summary,
            premortem_findings=premortem_findings,
        )

    # ------------------------------------------------------------------
    # Persistencia + Merkle
    # ------------------------------------------------------------------

    def _finalize(
        self,
        *,
        included: list[str],
        excluded: list[dict[str, Any]],
        passed: bool,
        pytest_summary: str,
        mypy_summary: str,
        premortem_findings: dict[str, Any] | None = None,
    ) -> BatchResult:
        result = BatchResult(
            id=str(uuid.uuid4())[:12],
            included=included,
            excluded=excluded,
            passed=passed,
            pytest_summary=pytest_summary,
            mypy_summary=mypy_summary,
            worktree_path=None,
            premortem=premortem_findings,
        )
        self._persist(result)
        self._merkle.log(
            action="cold_update.batch_validated",
            agent="cold_update_batcher",
            result="success" if passed else "failure",
            risk_level="high",
            payload={
                "batch_id": result.id,
                "included": included,
                "excluded": excluded,
                "passed": passed,
            },
        )
        return result

    def _load(self) -> dict[str, Any]:
        if not self._batches_file.exists():
            return {"batches": []}
        try:
            data: dict[str, Any] = json.loads(self._batches_file.read_text(encoding="utf-8"))
            if "batches" not in data:
                return {"batches": []}
            return data
        except Exception:
            return {"batches": []}

    def _persist(self, result: BatchResult) -> None:
        data = self._load()
        data["batches"].append(result.to_dict())
        self._batches_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Worktrees (mismo patron que ColdUpdateManager)
    # ------------------------------------------------------------------

    def _new_worktree_path(self) -> Path:
        return self._store_dir / f"worktree-batch-{uuid.uuid4().hex[:12]}"

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
        raise RuntimeError(f"Patch no aplicable en lote: {last_err[:500]}")

    def _remove_worktree(self, path: Path) -> None:
        if not path.exists():
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if path.exists() and path.resolve() != self._root.resolve():
            shutil.rmtree(path, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self._root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
