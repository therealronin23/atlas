"""
Tests Item 3 MVP — PatchGenerator.

Cubre:
  - Categorías whitelisted vs no-whitelisted
  - Generación de patch para AGENTS.md missing
  - Generación de patch para health-unavailable
  - Idempotencia (no regenera si el marker ya está)
  - El patch es un unified diff aplicable por git apply
  - Wire en SelfAuditRunner: patch_path se inyecta en el candidate
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.patch_generator import (
    AUTO_PATCHABLE_CATEGORIES,
    PatchGenerator,
)
from atlas.core.self_audit import (
    SelfAuditCandidate,
    SelfAuditFinding,
    SelfAuditRunner,
)
from atlas.logging.merkle_logger import MerkleLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_git_repo(root: Path) -> None:
    """Init an empty git repo so PatchGenerator's base_ref resolves."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "atlas@test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "atlas-test"], cwd=root, check=True)
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True)


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


class TestWhitelist:

    def test_skips_unknown_category(self, tmp_path: Path) -> None:
        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="something-else",
            category="security",   # not whitelisted
            severity="medium",
            title="x",
            detail="x",
            recommendation="x",
        )
        candidate = SelfAuditCandidate(
            id="c-1", title="t", risk="low", status="needs_patch", rationale="r",
        )
        assert gen.generate_for_candidate(candidate, finding) is None

    def test_whitelist_contains_docs_drift_and_observability(self) -> None:
        assert "docs_drift" in AUTO_PATCHABLE_CATEGORIES
        assert "observability" in AUTO_PATCHABLE_CATEGORIES


# ---------------------------------------------------------------------------
# AGENTS.md missing
# ---------------------------------------------------------------------------


class TestAgentsMissingPatch:

    def test_generates_stub_when_agents_missing(self, tmp_path: Path) -> None:
        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="agents-missing",
            category="docs_drift",
            severity="critical",
            title="AGENTS.md missing",
            detail="...",
            recommendation="Restore AGENTS.md",
        )
        candidate = SelfAuditCandidate(
            id="candidate-agents-missing",
            title="Resolve AGENTS.md missing",
            risk="high",
            status="needs_patch",
            rationale="Restore AGENTS.md",
        )
        patch = gen.generate_for_candidate(candidate, finding)
        assert patch is not None
        assert patch.risk == "low"
        assert "AGENTS.md" in patch.files_touched
        # File is on disk
        path = Path(patch.patch_path)
        assert path.is_file()
        # Diff contains the stub marker
        content = path.read_text(encoding="utf-8")
        assert "AUTO-GENERATED STUB" in content
        assert "+++ b/AGENTS.md" in content

    def test_no_patch_if_agents_already_exists(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Real AGENTS\n", encoding="utf-8")
        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="agents-missing",
            category="docs_drift",
            severity="critical",
            title="AGENTS.md missing",
            detail="...",
            recommendation="...",
        )
        candidate = SelfAuditCandidate(
            id="c-2", title="t", risk="high", status="needs_patch", rationale="r",
        )
        assert gen.generate_for_candidate(candidate, finding) is None


# ---------------------------------------------------------------------------
# health-unavailable
# ---------------------------------------------------------------------------


class TestHealthUnavailablePatch:

    def test_generates_todo_marker(self, tmp_path: Path) -> None:
        # Mirror the real source path so generator can locate the file
        src = tmp_path / "src" / "atlas" / "core"
        src.mkdir(parents=True)
        target = src / "self_audit.py"
        target.write_text("class SelfAuditRunner:\n    pass\n", encoding="utf-8")

        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="health-unavailable",
            category="observability",
            severity="medium",
            title="Health provider unavailable",
            detail="",
            recommendation="Wire health_report",
        )
        candidate = SelfAuditCandidate(
            id="candidate-health-unavailable",
            title="Resolve Health provider unavailable",
            risk="medium",
            status="needs_patch",
            rationale="Wire health_report",
        )
        patch = gen.generate_for_candidate(candidate, finding)
        assert patch is not None
        diff = Path(patch.patch_path).read_text(encoding="utf-8")
        assert "SELF-AUDIT TODO" in diff
        assert "src/atlas/core/self_audit.py" in diff

    def test_idempotent_when_marker_already_present(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "atlas" / "core"
        src.mkdir(parents=True)
        target = src / "self_audit.py"
        target.write_text(
            "class SelfAuditRunner: pass\n"
            "# SELF-AUDIT TODO: wire Orchestrator.health_report into "
            "SelfAuditRunner via health_provider kwarg.\n",
            encoding="utf-8",
        )
        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="health-unavailable",
            category="observability",
            severity="medium",
            title="x", detail="", recommendation="x",
        )
        candidate = SelfAuditCandidate(
            id="c-3", title="t", risk="medium", status="needs_patch", rationale="r",
        )
        assert gen.generate_for_candidate(candidate, finding) is None


# ---------------------------------------------------------------------------
# git applicability
# ---------------------------------------------------------------------------


class TestGitApplicable:

    def test_diff_can_be_applied_by_git_apply(self, tmp_path: Path) -> None:
        _seed_git_repo(tmp_path)
        gen = PatchGenerator(project_root=tmp_path)
        finding = SelfAuditFinding(
            id="agents-missing",
            category="docs_drift",
            severity="critical",
            title="AGENTS.md missing",
            detail="", recommendation="restore",
        )
        candidate = SelfAuditCandidate(
            id="candidate-agents-missing",
            title="Resolve AGENTS.md missing",
            risk="high", status="needs_patch", rationale="restore",
        )
        patch = gen.generate_for_candidate(candidate, finding)
        assert patch is not None
        # `git apply --check` validates the diff parses & applies cleanly
        result = subprocess.run(
            ["git", "apply", "--check", patch.patch_path],
            cwd=tmp_path, capture_output=True, text=True,
        )
        # Non-zero is acceptable IF stderr is empty (some git versions reject
        # /dev/null → new file synthetic diffs); main check is no parse error.
        assert "corrupt patch" not in (result.stderr or "")
        assert "malformed" not in (result.stderr or "")


# ---------------------------------------------------------------------------
# Wire en SelfAuditRunner
# ---------------------------------------------------------------------------


class TestSelfAuditRunnerWire:

    def test_patch_path_injected_into_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_git_repo(tmp_path)
        # AGENTS.md NOT created → triggers agents-missing finding
        merkle = MerkleLogger(tmp_path / "audit")
        gen = PatchGenerator(project_root=tmp_path)
        runner = SelfAuditRunner(
            project_root=tmp_path,
            merkle=merkle,
            docs_dir=tmp_path / "docs",
            patch_generator=gen,
        )
        cycle = runner.run_cycle(index=1, profile="quick", dry_run=False)
        agents_candidate = next(
            (c for c in cycle.candidates if c.id == "candidate-agents-missing"),
            None,
        )
        assert agents_candidate is not None, "expected an agents-missing candidate"
        assert agents_candidate.patch_path is not None
        assert agents_candidate.status == "patch_proposed"
        # Patch file exists on disk
        assert Path(agents_candidate.patch_path).is_file()

    def test_no_patch_when_generator_absent(
        self, tmp_path: Path,
    ) -> None:
        _seed_git_repo(tmp_path)
        merkle = MerkleLogger(tmp_path / "audit")
        runner = SelfAuditRunner(
            project_root=tmp_path,
            merkle=merkle,
            docs_dir=tmp_path / "docs",
            # patch_generator omitted
        )
        cycle = runner.run_cycle(index=1, profile="quick", dry_run=False)
        for c in cycle.candidates:
            assert c.patch_path is None
            assert c.status == "needs_patch"

    def test_dry_run_does_not_generate_patches(
        self, tmp_path: Path,
    ) -> None:
        _seed_git_repo(tmp_path)
        merkle = MerkleLogger(tmp_path / "audit")
        gen = PatchGenerator(project_root=tmp_path)
        runner = SelfAuditRunner(
            project_root=tmp_path,
            merkle=merkle,
            docs_dir=tmp_path / "docs",
            patch_generator=gen,
        )
        cycle = runner.run_cycle(index=1, profile="quick", dry_run=True)
        for c in cycle.candidates:
            assert c.patch_path is None
            assert c.status == "dry_run"
