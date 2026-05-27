"""
Atlas Core — PatchGenerator (Item 3 MVP).

Auto-generate cold-update patches from SelfAuditCandidate objects.
The patches are stored as `.patch` files for HITL review — NO hot-apply.

The generator is intentionally conservative:
- Only a small whitelist of categories is auto-patchable.
- Each generated patch is a minimal change (add TODO/docstring, append
  a note to a missing doc) — never refactors logic, never deletes code.
- Anything outside the whitelist returns None → manual review required.

Design choices:
- Patches are unified diffs in plain text — no git commands required.
- Patch files land in a workspace `patches/` dir so they can be picked
  up by ColdUpdateManager.propose(patch_path=...).
- The generator does NOT touch the working tree; it only writes the
  patch file alongside a base hash for traceability.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.self_audit import SelfAuditCandidate, SelfAuditFinding

_log = logging.getLogger(__name__)


# Categories whose findings produce a deterministic, minimal patch.
# Anything else → None (HITL must author the patch manually).
AUTO_PATCHABLE_CATEGORIES = {
    "docs_drift",        # Append marker to missing doc
    "observability",     # Add TODO in source for a missing instrument
}


@dataclass
class GeneratedPatch:
    """A single auto-generated patch awaiting HITL review."""

    id: str
    candidate_id: str
    category: str
    title: str
    risk: str                                       # low | medium | high | critical
    patch_path: str                                 # absolute path to the .patch file
    base_ref: str                                   # git rev that the patch targets
    files_touched: list[str] = field(default_factory=list)
    rationale: str = ""
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "category": self.category,
            "title": self.title,
            "risk": self.risk,
            "patch_path": self.patch_path,
            "base_ref": self.base_ref,
            "files_touched": list(self.files_touched),
            "rationale": self.rationale,
            "generated_at": self.generated_at,
        }


class PatchGenerator:
    """Generate small, reviewable patches from self-audit candidates.

    Usage:
        gen = PatchGenerator(project_root=Path("/home/ronin/proyectos/atlas-core"))
        patch = gen.generate_for_candidate(candidate, finding)
        if patch:
            ColdUpdateManager.propose(
                intent=patch.title,
                patch_path=Path(patch.patch_path),
                origin="self_audit",
                risk=patch.risk,
            )

    The generator NEVER applies patches — that's ColdUpdateManager's job
    after HITL approval.
    """

    def __init__(self, project_root: Path, *, base_ref: str = "HEAD") -> None:
        self._root = project_root.resolve()
        self._base_ref = base_ref
        self._patches_dir = self._root / "patches" / "self_audit"
        self._patches_dir.mkdir(parents=True, exist_ok=True)

    @property
    def patches_dir(self) -> Path:
        return self._patches_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_for_candidate(
        self,
        candidate: SelfAuditCandidate,
        finding: SelfAuditFinding,
    ) -> GeneratedPatch | None:
        """Attempt to auto-generate a patch. Returns None if not safe to auto-patch."""
        if finding.category not in AUTO_PATCHABLE_CATEGORIES:
            _log.debug(
                "patch_generator: skipping candidate %s (category %s not whitelisted)",
                candidate.id,
                finding.category,
            )
            return None

        if finding.id == "agents-missing":
            return self._patch_agents_missing(candidate, finding)
        if finding.id == "health-unavailable":
            return self._patch_health_unavailable(candidate, finding)

        # Whitelisted category but no concrete generator yet → manual review
        return None

    # ------------------------------------------------------------------
    # Concrete generators
    # ------------------------------------------------------------------

    def _patch_agents_missing(
        self,
        candidate: SelfAuditCandidate,
        finding: SelfAuditFinding,
    ) -> GeneratedPatch | None:
        """Stub AGENTS.md if missing — minimal so HITL can flesh it out."""
        target = self._root / "AGENTS.md"
        if target.exists():
            return None  # No-op: file is already there
        stub = (
            "# ATLAS CORE — Context for AI tools\n\n"
            "> AUTO-GENERATED STUB by self-audit. Replace with real content.\n\n"
            "## Project Status\n\n"
            "- (pending) — file restored by self-audit on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.\n"
        )
        return self._write_patch(
            candidate=candidate,
            finding=finding,
            target_rel="AGENTS.md",
            before="",
            after=stub,
            risk="low",
        )

    def _patch_health_unavailable(
        self,
        candidate: SelfAuditCandidate,
        finding: SelfAuditFinding,
    ) -> GeneratedPatch | None:
        """Append a TODO marker in self_audit.py so future cycles know to wire health."""
        target_rel = "src/atlas/core/self_audit.py"
        target = self._root / target_rel
        if not target.is_file():
            return None
        original = target.read_text(encoding="utf-8")
        marker = (
            "\n# SELF-AUDIT TODO: wire Orchestrator.health_report into "
            "SelfAuditRunner via health_provider kwarg.\n"
        )
        if marker in original:
            return None
        patched = original.rstrip() + marker
        return self._write_patch(
            candidate=candidate,
            finding=finding,
            target_rel=target_rel,
            before=original,
            after=patched,
            risk="low",
        )

    # ------------------------------------------------------------------
    # Diff + file helpers
    # ------------------------------------------------------------------

    def _write_patch(
        self,
        *,
        candidate: SelfAuditCandidate,
        finding: SelfAuditFinding,
        target_rel: str,
        before: str,
        after: str,
        risk: str,
    ) -> GeneratedPatch:
        diff = self._unified_diff(target_rel, before, after)
        patch_id = uuid.uuid4().hex[:8]
        digest = hashlib.sha256(target_rel.encode()).hexdigest()[:8]
        filename = f"{candidate.id}-{digest}-{patch_id}.patch"
        path = self._patches_dir / filename
        path.write_text(diff, encoding="utf-8")
        return GeneratedPatch(
            id=patch_id,
            candidate_id=candidate.id,
            category=finding.category,
            title=f"{finding.title} → auto-stub",
            risk=risk,
            patch_path=str(path),
            base_ref=self._base_ref,
            files_touched=[target_rel],
            rationale=finding.recommendation,
        )

    @staticmethod
    def _unified_diff(target_rel: str, before: str, after: str) -> str:
        """Produce a git-applicable unified diff for target_rel."""
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        # Ensure trailing newline so the diff doesn't say "No newline at end of file"
        if before and not before.endswith("\n"):
            before_lines[-1] = before_lines[-1] + "\n"
        if after and not after.endswith("\n"):
            after_lines[-1] = after_lines[-1] + "\n"
        diff_lines = list(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{target_rel}",
                tofile=f"b/{target_rel}",
                lineterm="\n",
            )
        )
        if not diff_lines:
            return ""
        # Prepend git-style header so `git apply` recognizes new files
        header = (
            f"diff --git a/{target_rel} b/{target_rel}\n"
            f"--- a/{target_rel}\n"
            f"+++ b/{target_rel}\n"
        )
        # difflib already emits --- / +++ headers; replace them with our git-style header
        # Find the first line that isn't a "---" header
        start = 0
        for i, line in enumerate(diff_lines):
            if line.startswith("@@"):
                start = i
                break
        body = "".join(diff_lines[start:])
        return header + body
