"""Atlas 24h Self-Audit Loop tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_audit import SelfAuditRunner
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='atlas-test'\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b.c", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return root


@pytest.fixture
def runner(git_project: Path, tmp_path: Path) -> SelfAuditRunner:
    merkle = MerkleLogger(tmp_path / "atlas" / "memory" / "audit")
    return SelfAuditRunner(
        git_project,
        merkle,
        health_provider=lambda: {"governance_ok": True, "merkle_chain_ok": True},
    )


def test_cycle_creates_report_without_tracked_worktree_changes(
    runner: SelfAuditRunner,
    git_project: Path,
) -> None:
    report = runner.run(hours=1, max_cycles=1, cycle_interval_minutes=60, dry_run=True)

    latest = git_project / "docs" / "self_audit_latest.json"
    dated = git_project / "docs" / "self_audit_2026-05-25.md"
    assert report.status == "completed"
    assert latest.exists()
    assert dated.exists() or any((git_project / "docs").glob("self_audit_*.md"))

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=git_project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert status
    assert all(line.startswith("?? ") for line in status)


def test_status_proposals_and_stop_are_idempotent(runner: SelfAuditRunner) -> None:
    assert runner.status()["latest_report"] is None
    assert runner.proposals() == []

    runner.stop()
    runner.stop()
    assert runner.status()["stop_requested"] is True


def test_diagnoses_claude_untracked(runner: SelfAuditRunner, git_project: Path) -> None:
    (git_project / ".claude").mkdir()
    (git_project / ".claude" / "local.json").write_text("{}", encoding="utf-8")
    report = runner.run(hours=1, max_cycles=1, dry_run=True)

    findings = report.cycles[0].findings
    assert any(f.id == "claude-untracked" for f in findings)
    candidates = report.cycles[0].candidates
    assert any(c.id == "candidate-claude-untracked" for c in candidates)


def test_missing_health_provider_becomes_observability_finding(
    git_project: Path,
    tmp_path: Path,
) -> None:
    merkle = MerkleLogger(tmp_path / "audit")
    runner = SelfAuditRunner(git_project, merkle)

    report = runner.run(hours=1, max_cycles=1, dry_run=False)

    assert any(f.id == "health-unavailable" for f in report.cycles[0].findings)
    assert any(c.status == "needs_patch" for c in report.cycles[0].candidates)


def test_report_roundtrip_json(runner: SelfAuditRunner) -> None:
    report = runner.run(hours=1, max_cycles=1, dry_run=True)
    loaded = runner.latest_report()

    assert loaded is not None
    assert loaded["id"] == report.id
    assert json.loads((runner._state_file).read_text(encoding="utf-8"))["status"] == "completed"
