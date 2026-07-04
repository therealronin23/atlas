"""lesson_runner — ejecuta pytest en dos worktrees (before/after un fix_commit)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from atlas.core.lesson_store import Lesson, LessonPromoter, LessonStore, ProveItResult
from atlas.security.bwrap_jail import BwrapJail, BwrapUnavailableError

__all__ = ["LessonRunner", "WorktreeError", "run_and_promote", "promote_if_fixed"]

_log = logging.getLogger(__name__)


class WorktreeError(RuntimeError):
    """Falla al crear/eliminar un git worktree."""


class LessonRunner:
    def __init__(self, *, repo_root: Path | None = None, timeout_s: int = 120) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _add_worktree(self, wt_path: str, commit: str) -> None:
        result = subprocess.run(
            ["git", "worktree", "add", wt_path, commit],
            cwd=self._repo_root,
            capture_output=True,
        )
        if result.returncode != 0:
            raise WorktreeError(
                f"git worktree add failed for {commit!r}: "
                f"{result.stderr.decode(errors='replace').strip()}"
            )

    def _remove_worktree(self, wt_path: str) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            cwd=self._repo_root,
            capture_output=True,
        )

    def _run_pytest(self, test_path: str, wt_path: str) -> int:
        """Corre pytest; devuelve returncode."""
        if BwrapJail.is_available():
            script = (
                "import subprocess, sys\n"
                f"r = subprocess.run(['pytest', {test_path!r}, '-x', '-q'], cwd={wt_path!r})\n"
                "sys.exit(r.returncode)\n"
            )
            try:
                jail = BwrapJail(python_bin="python3")
                bwrap_result = jail.run(script, timeout_s=self._timeout_s, extra_env={})
                return bwrap_result.returncode
            except BwrapUnavailableError:
                pass  # fallback a subprocess directo

        result = subprocess.run(
            ["pytest", test_path, "-x", "-q"],
            cwd=wt_path,
        )
        return result.returncode

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def run(self, test_path: str, fix_commit: str) -> ProveItResult:
        with tempfile.TemporaryDirectory(prefix="atlas_lesson_") as tmpdir:
            wt_before = str(Path(tmpdir) / "before")
            wt_after = str(Path(tmpdir) / "after")

            self._add_worktree(wt_before, f"{fix_commit}^")
            try:
                self._add_worktree(wt_after, fix_commit)
                try:
                    rc_before = self._run_pytest(test_path, wt_before)
                    rc_after = self._run_pytest(test_path, wt_after)
                finally:
                    self._remove_worktree(wt_after)
            finally:
                self._remove_worktree(wt_before)

        return ProveItResult(
            test_path=test_path,
            fix_commit=fix_commit,
            failed_before=rc_before != 0,
            passes_after=rc_after == 0,
        )

    def run_and_promote(
        self,
        test_path: str,
        fix_commit: str,
        *,
        store: LessonStore,
        failure_id: str,
        title: str,
        detection_heuristic: str,
        avoid_pattern: str,
        tags: tuple[str, ...] = (),
    ) -> tuple[ProveItResult, Lesson | None]:
        """Ejecuta el prove-it y, si pasa (rojo→verde), persiste la lección.

        Devuelve (ProveItResult, Lesson|None). Lesson es None si el test no
        demuestra rojo-antes/verde-ahora — no se persiste nada en ese caso.
        """
        result = self.run(test_path, fix_commit)
        promoter = LessonPromoter(store)
        lesson = promoter.promote_failure(
            failure_id=failure_id,
            title=title,
            detection_heuristic=detection_heuristic,
            avoid_pattern=avoid_pattern,
            regression_test_path=test_path,
            prove_it=result,
            tags=tags,
        )
        return result, lesson


def promote_if_fixed(
    failure_id: str,
    fix_commit: str,
    store: "LessonStore",
    *,
    title: str,
    detection_heuristic: str,
    avoid_pattern: str,
    test_path: str,
    tags: tuple[str, ...] = (),
    repo_root: Path | None = None,
    timeout_s: int = 60,
) -> "Lesson | None":
    """Dado un failure_id y su fix_commit, corre el runner prove-it y si pasa
    promociona a lección. Devuelve la Lesson creada o None si prove-it falla
    o ya existe una lección con ese failure_id en el store.
    """
    # Idempotencia: si ya existe una lección con este failure_id, no duplicar.
    needle = f"failure:{failure_id}"
    for existing in store.all():
        if needle in existing.source_refs:
            return None

    runner = LessonRunner(repo_root=repo_root or Path.cwd(), timeout_s=timeout_s)
    _result, lesson = runner.run_and_promote(
        test_path=test_path,
        fix_commit=fix_commit,
        store=store,
        failure_id=failure_id,
        title=title,
        detection_heuristic=detection_heuristic,
        avoid_pattern=avoid_pattern,
        tags=tags,
    )
    return lesson
