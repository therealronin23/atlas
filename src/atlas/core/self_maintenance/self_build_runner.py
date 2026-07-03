"""
Atlas Core — SelfBuildRunner: pegamento entre backlog, ToolCoder y ColdUpdateManager.

Toma un BacklogItem pendiente, deriva un test_cmd razonable, delega la
codificación real a ToolCoder (bucle agéntico de tool-calling ya existente),
y si los tests pasan genera un patch real y lo PROPONE a ColdUpdateManager
con origin="self_audit". Por invariante CVE-HITL (G0.8), origin="self_audit"
NUNCA dispara tier1_auto_apply — toda propuesta de self-build requiere
aprobación humana explícita (approve_pending()/approve() aparte de este
runner). Este módulo solo PROPONE, nunca aplica ni marca items como "done".
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

from atlas.core.cold_update_manager import ColdUpdateManager, ColdUpdateProposal
from atlas.core.inference_hub import InferenceHub
from atlas.core.self_maintenance.backlog import BacklogItem
from atlas.core.tool_coder import ToolCoder

__all__ = ["SelfBuildRunner"]

logger = logging.getLogger(__name__)


class SelfBuildRunner:
    """Conecta backlog -> ToolCoder -> ColdUpdateManager (self_audit, siempre HITL)."""

    def __init__(
        self,
        repo_root: Path,
        hub: InferenceHub,
        cold_update_manager: ColdUpdateManager,
        backlog_path: Path = Path("docs/backlog.yaml"),
        *,
        tool_coder_factory: Callable[..., ToolCoder] = ToolCoder,
    ) -> None:
        self._repo_root = repo_root
        self._hub = hub
        self._cold_update = cold_update_manager
        self._backlog_path = backlog_path
        self._tool_coder_factory = tool_coder_factory

    # ------------------------------------------------------------------
    # derive_test_cmd
    # ------------------------------------------------------------------

    def derive_test_cmd(self, item: BacklogItem) -> list[str]:
        """Deriva el comando de test para un BacklogItem.

        Prioridad: 1) campo test_cmd explícito del item; 2) heurística simple
        de nombre de archivo (NO es NLP, solo un glob por convención de
        nombres: tests/test_{id con '-' -> '_'}*.py); 3) fallback a la suite
        completa (`pytest -q`).
        """
        if item.test_cmd:
            return list(item.test_cmd)

        slug = item.id.replace("-", "_")
        tests_dir = self._repo_root / "tests"
        if tests_dir.is_dir():
            matches = sorted(tests_dir.glob(f"test_{slug}*.py"))
            if matches:
                rel = matches[0].relative_to(self._repo_root)
                return ["pytest", str(rel), "-q"]

        return ["pytest", "-q"]

    # ------------------------------------------------------------------
    # run_item
    # ------------------------------------------------------------------

    def run_item(self, item: BacklogItem, *, max_iterations: int = 3) -> dict[str, Any]:
        """Ejecuta ToolCoder sobre el item y, si los tests pasan, PROPONE el
        patch a ColdUpdateManager (origin="self_audit" -> requiere HITL).

        Nunca marca el item como "done": eso requiere aprobación humana del
        proposal, fuera del alcance de este método.
        """
        test_cmd = self.derive_test_cmd(item)
        task = f"{item.title}\n\n{item.why}\n\nCriterio de aceptación:\n{item.acceptance}"

        baseline = self._git_status_lines()
        coder = self._tool_coder_factory(self._hub, repo_root=self._repo_root)
        coder_result = coder.code(
            task,
            context_files=self._expand_targets(item.targets),
            test_cmd=test_cmd,
            max_iterations=max_iterations,
        )

        if not coder_result.success:
            self._revert_new_changes(baseline)
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": coder_result.error or coder_result.test_output or "sin detalle",
            }

        patch_path = self._write_patch()
        if patch_path is None:
            self._revert_new_changes(baseline)
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": "tests pasaron pero no se pudo generar diff (sin cambios detectables en git)",
            }

        cycle_summary = {
            "success": coder_result.success,
            "iterations": coder_result.iterations,
            "files_changed": list(coder_result.files_changed),
            "suspicious_no_op": getattr(coder_result, "suspicious_no_op", False),
        }

        proposal: ColdUpdateProposal = self._cold_update.propose(
            intent=item.title,
            patch_path=patch_path,
            origin="self_audit",
            risk="medium",
            evidence={
                "backlog_item_id": item.id,
                "cycle_result": cycle_summary,
            },
        )

        return {
            "item_id": item.id,
            "proposal_id": proposal.id,
            "status": "proposed",
            "detail": cycle_summary,
        }

    def _expand_targets(self, targets: tuple[str, ...] | list[str]) -> list[str]:
        """Expande targets que son directorios (terminan en '/') a los .py
        que contienen (no recursivo — un target de directorio en el backlog
        describe un módulo plano, no un árbol completo). Los targets que ya
        son ficheros pasan intactos."""
        out: list[str] = []
        for target in targets:
            if target.endswith("/"):
                abs_dir = self._repo_root / target
                if abs_dir.is_dir():
                    out.extend(
                        str(p.relative_to(self._repo_root))
                        for p in sorted(abs_dir.glob("*.py"))
                    )
                continue
            out.append(target)
        return out

    def _git_status_lines(self) -> set[str]:
        """Snapshot de `git status --porcelain` (líneas crudas) para poder
        detectar y revertir SOLO lo que ToolCoder ensucie en un intento
        fallido — nunca dejar el árbol de trabajo sucio tras un fracaso."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self._repo_root, capture_output=True, text=True, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return set()
        return set(result.stdout.splitlines())

    def _revert_new_changes(self, baseline: set[str]) -> None:
        """Tras un intento fallido de ToolCoder: revierte ficheros trackeados
        recién modificados y borra ficheros nuevos sin trackear que NO
        estaban en el `baseline` — deja el árbol de trabajo exactamente como
        antes del intento, nunca a medias."""
        current = self._git_status_lines()
        for line in current - baseline:
            if len(line) < 4:
                continue
            status, rel_path = line[:2], line[3:]
            abs_path = self._repo_root / rel_path
            if status == "??":
                if abs_path.is_file():
                    abs_path.unlink()
                continue
            subprocess.run(
                ["git", "checkout", "--", rel_path],
                cwd=self._repo_root, capture_output=True, text=True, check=False,
            )

    def _write_patch(self) -> Path | None:
        """Genera un .patch con `git diff` del estado actual del repo_root.

        Devuelve None si no hay diff (nada que proponer) o si git falla.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("SelfBuildRunner: git diff falló (%s)", exc)
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None

        tmp_dir = Path(tempfile.mkdtemp(prefix="self_build_patch_"))
        patch_path = tmp_dir / "change.patch"
        patch_path.write_text(result.stdout, encoding="utf-8")
        return patch_path

    # ------------------------------------------------------------------
    # update_backlog_status
    # ------------------------------------------------------------------

    def update_backlog_status(self, item_id: str, new_status: str) -> None:
        """Reescribe SOLO el campo `status` del item `item_id` en el YAML.

        Manipulación de texto línea a línea (no ruamel: el proyecto ya usa
        yaml.safe_load/safe_dump en otros sitios, p.ej. backlog.py) para NO
        reordenar ni reformatear el resto del archivo — solo se toca la
        línea `status: <valor>` dentro del bloque del item indicado.
        """
        text = self._backlog_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)

        id_re = re.compile(r'^\s*-?\s*id:\s*["\']?' + re.escape(item_id) + r'["\']?\s*$')
        status_re = re.compile(r"^(\s*status:\s*)(\S+)(.*)$")

        in_target_item = False
        out_lines: list[str] = []
        for line in lines:
            if re.match(r"^\s*-\s*id:\s*", line):
                in_target_item = bool(id_re.match(line.rstrip("\n")))
            if in_target_item:
                m = status_re.match(line.rstrip("\n"))
                if m:
                    newline = "\n" if line.endswith("\n") else ""
                    out_lines.append(f"{m.group(1)}{new_status}{m.group(3)}{newline}")
                    in_target_item = False
                    continue
            out_lines.append(line)

        self._backlog_path.write_text("".join(out_lines), encoding="utf-8")
