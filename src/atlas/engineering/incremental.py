"""Read-only preparation of an ancestry-verified incremental review diff.

This module composes the explicit baseline journal with Git's object database.
It never reads the working tree for review content, runs candidate code, writes
to the repository, invokes external diff/textconv hooks, or promotes a review.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from atlas.core.git_env import clean_git_env
from atlas.engineering.baselines import (
    EngineeringReviewBaselineStore,
    IncrementalReviewSelection,
)
from atlas.engineering.review import EngineeringReviewRequest


class IncrementalReviewPreparationError(RuntimeError):
    """A bounded incremental diff could not be proven safe to hand to review."""


@dataclass(frozen=True)
class PreparedIncrementalReview:
    """A verified request, or an explicit no-op for an accepted candidate."""

    selection: IncrementalReviewSelection
    request: EngineeringReviewRequest | None
    ancestry_verified: bool


_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


class EngineeringIncrementalReviewPreparer:
    """Prepare a bounded Git-object diff after baseline selection.

    The caller owns worktree creation and any later reviewer execution.  This
    preparer only reads named commits, uses an explicitly sanitized Git
    environment, and keeps all command diagnostics out of the resulting review
    request.
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        baselines: EngineeringReviewBaselineStore,
        max_diff_bytes: int = 2_000_000,
        timeout_s: int = 30,
    ) -> None:
        if max_diff_bytes <= 0:
            raise ValueError("max_diff_bytes must be positive")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._repo_root = repo_root.resolve()
        self._baselines = baselines
        self._max_diff_bytes = max_diff_bytes
        self._timeout_s = timeout_s

    def prepare(self, request: EngineeringReviewRequest) -> PreparedIncrementalReview:
        """Select, verify, and read the next diff without executing a candidate."""

        selection = self._baselines.select(request)
        if not selection.review_required:
            return PreparedIncrementalReview(
                selection=selection,
                request=None,
                ancestry_verified=False,
            )
        base_revision = selection.base_revision
        candidate_revision = request.candidate_revision
        if base_revision is None or candidate_revision is None:
            raise IncrementalReviewPreparationError(
                "incremental review requires both base and candidate revisions"
            )
        self._validate_commit_id(base_revision, "base revision")
        self._validate_commit_id(candidate_revision, "candidate revision")
        self._ensure_git_worktree()
        self._verify_commit(base_revision, "base revision")
        self._verify_commit(candidate_revision, "candidate revision")
        self._verify_ancestor(base_revision, candidate_revision)
        diff = self._read_diff(base_revision, candidate_revision)
        return PreparedIncrementalReview(
            selection=selection,
            request=replace(request, base_revision=base_revision, diff=diff),
            ancestry_verified=True,
        )

    @staticmethod
    def _validate_commit_id(revision: str, label: str) -> None:
        if not _COMMIT_SHA.fullmatch(revision):
            raise IncrementalReviewPreparationError(
                f"{label} must be an immutable commit SHA"
            )

    def _ensure_git_worktree(self) -> None:
        if not self._repo_root.is_dir():
            raise IncrementalReviewPreparationError("review repository root is unavailable")
        result = self._git(["git", "rev-parse", "--is-inside-work-tree"])
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise IncrementalReviewPreparationError("review repository root is not a Git worktree")

    def _verify_commit(self, revision: str, label: str) -> None:
        result = self._git(["git", "rev-parse", "--verify", f"{revision}^{{commit}}"])
        if result.returncode != 0:
            raise IncrementalReviewPreparationError(f"{label} does not resolve to a commit")

    def _verify_ancestor(self, base_revision: str, candidate_revision: str) -> None:
        result = self._git(
            ["git", "merge-base", "--is-ancestor", base_revision, candidate_revision]
        )
        if result.returncode == 0:
            return
        if result.returncode == 1:
            raise IncrementalReviewPreparationError(
                "selected baseline is not an ancestor of the candidate"
            )
        raise IncrementalReviewPreparationError("Git could not verify baseline ancestry")

    def _read_diff(self, base_revision: str, candidate_revision: str) -> str:
        result = self._git(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--unified=3",
                base_revision,
                candidate_revision,
                "--",
            ]
        )
        if result.returncode != 0:
            raise IncrementalReviewPreparationError("Git could not read the incremental diff")
        diff = result.stdout
        if len(diff.encode("utf-8")) > self._max_diff_bytes:
            raise IncrementalReviewPreparationError(
                f"incremental diff exceeds {self._max_diff_bytes} bytes"
            )
        return diff

    def _git(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=self._repo_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IncrementalReviewPreparationError(
                f"Git incremental review preparation failed with {type(exc).__name__}"
            ) from exc
