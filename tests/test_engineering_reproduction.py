"""Tests for fail-closed isolated engineering reproductions."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from atlas.core.git_env import clean_git_env
from atlas.engineering.reproduction import (
    EngineeringReproductionRequest,
    EngineeringReproductionRunner,
    ReproductionStatus,
)
from atlas.logging.merkle_logger import AuditRecord
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.bwrap_jail import BwrapUnavailableError


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_example.py").write_text("def test_example():\n    assert True\n")
    _git(repo, "add", "tests/test_example.py")
    _git(repo, "commit", "-qm", "candidate")
    return repo, _git(repo, "rev-parse", "HEAD")


def _request(candidate: str, *, targets: tuple[str, ...] = ("tests/test_example.py",)) -> EngineeringReproductionRequest:
    return EngineeringReproductionRequest(
        run_id="run_reproduction_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision=candidate,
        candidate_revision=candidate,
        correlation_id="reproduction_001",
        test_targets=targets,
        at="2026-07-29T18:00:00+00:00",
    )


class _Audit:
    def __init__(self, timeline: list[str], *, fail_on: int | None = None) -> None:
        self.timeline = timeline
        self.fail_on = fail_on
        self.records: list[dict[str, object]] = []

    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict[str, object] | None = None,
        task_id: str | None = None,
    ) -> AuditRecord:
        self.timeline.append(action)
        self.records.append(
            {
                "action": action,
                "agent": agent,
                "result": result,
                "risk_level": risk_level,
                "payload": payload or {},
                "task_id": task_id,
            }
        )
        if self.fail_on == len(self.records):
            raise OSError("audit storage unavailable")
        return AuditRecord(
            action=action,
            agent=agent,
            result=result,
            risk_level=risk_level,
            payload=payload or {},
            task_id=task_id,
        )


class _JailResult:
    def __init__(self, *, returncode: int = 0, stdout: str = "1 passed", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = 12


class _Jail:
    def __init__(self, timeline: list[str], *, require_audit_start: bool = True) -> None:
        self.timeline = timeline
        self._require_audit_start = require_audit_start
        self.calls: list[dict[str, object]] = []

    def run_command(
        self,
        command: tuple[str, ...],
        *,
        working_dir: Path,
        working_dir_writable: bool,
        read_only_paths: tuple[Path, ...],
        timeout_s: int,
        extra_env: dict[str, str],
    ) -> _JailResult:
        if self._require_audit_start:
            assert self.timeline == ["engineering.reproduction.started"]
        self.timeline.append("jail")
        self.calls.append(
            {
                "command": command,
                "working_dir": working_dir,
                "working_dir_writable": working_dir_writable,
                "read_only_paths": read_only_paths,
                "timeout_s": timeout_s,
                "extra_env": extra_env,
            }
        )
        return _JailResult()


def test_reproduction_is_audited_before_a_read_only_jail_run(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    audit = _Audit(timeline)
    jail = _Jail(timeline)
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=audit,
        jail=jail,
    )

    report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.PASSED
    assert report.execution_completed is True
    assert report.audit_start_hash
    assert report.audit_result_hash
    assert timeline == [
        "engineering.reproduction.started",
        "jail",
        "engineering.reproduction.completed",
    ]
    call = jail.calls[0]
    assert call["working_dir"] != repo
    assert call["working_dir_writable"] is False
    assert call["command"][1:5] == ("-m", "pytest", "-q", "--tb=line")
    assert call["extra_env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert call["extra_env"]["ATLAS_MEMORY_VECTOR"] == "0"
    assert "stdout" not in audit.records[-1]["payload"]
    assert "stderr" not in audit.records[-1]["payload"]


def test_invalid_test_target_is_rejected_before_audit_or_worktree(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    audit = _Audit(timeline)
    jail = _Jail(timeline)
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=audit,
        jail=jail,
    )

    report = runner.reproduce(_request(candidate, targets=("../.env",)))

    assert report.status is ReproductionStatus.REJECTED
    assert report.execution_completed is False
    assert timeline == []
    assert jail.calls == []

    empty_selector = runner.reproduce(
        _request(candidate, targets=("tests/test_example.py::",))
    )

    assert empty_selector.status is ReproductionStatus.REJECTED
    assert timeline == []
    assert jail.calls == []


def test_audit_failure_before_execution_fails_closed(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    audit = _Audit(timeline, fail_on=1)
    jail = _Jail(timeline)
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=audit,
        jail=jail,
    )

    report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.AUDIT_UNAVAILABLE
    assert report.execution_completed is False
    assert jail.calls == []


def test_reproduction_merkle_receipts_exclude_captured_output(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    merkle = MerkleLogger(tmp_path / "audit")
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=merkle,
        jail=_Jail(timeline, require_audit_start=False),
    )

    report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.PASSED
    ok, reason = merkle.verify_chain()
    assert ok, reason
    records = merkle.read_all()
    assert [record.action for record in records] == [
        "engineering.reproduction.started",
        "engineering.reproduction.completed",
    ]
    assert "1 passed" not in str(records[-1].payload)


class _UnavailableJail(_Jail):
    def run_command(
        self,
        command: tuple[str, ...],
        *,
        working_dir: Path,
        working_dir_writable: bool,
        read_only_paths: tuple[Path, ...],
        timeout_s: int,
        extra_env: dict[str, str],
    ) -> _JailResult:
        raise BwrapUnavailableError("no bubblewrap")


def test_missing_jail_is_reported_without_an_execution_claim(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    audit = _Audit(timeline)
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=audit,
        jail=_UnavailableJail(timeline),
    )

    report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.UNAVAILABLE
    assert report.execution_completed is False
    assert report.test_exit is None
    assert timeline == [
        "engineering.reproduction.started",
        "engineering.reproduction.completed",
    ]


class _StaticWorktrees:
    def __init__(self, worktree: Path) -> None:
        self._worktree = worktree

    @contextmanager
    def session(self, name: str, *, base_ref: str = "HEAD") -> Iterator[Path]:
        assert name.startswith("engineering-reproduction-")
        assert len(base_ref) == 40
        yield self._worktree


def test_foreign_ephemeral_worktree_is_rejected_before_jail_execution(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path / "primary")
    foreign_repo, foreign_candidate = _repository(tmp_path / "foreign")
    foreign_manager = WorktreeManager(
        foreign_repo,
        worktrees_dir=tmp_path / "foreign-worktrees",
    )
    timeline: list[str] = []
    audit = _Audit(timeline)
    jail = _Jail(timeline)
    with foreign_manager.session("foreign", base_ref=foreign_candidate) as foreign_worktree:
        runner = EngineeringReproductionRunner(
            repo_root=repo,
            worktrees=_StaticWorktrees(foreign_worktree),
            audit=audit,
            jail=jail,
        )

        report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.UNAVAILABLE
    assert report.execution_completed is False
    assert jail.calls == []


def test_completion_audit_failure_never_promotes_a_completed_execution(tmp_path: Path) -> None:
    from atlas.core.swarm_backend import WorktreeManager

    repo, candidate = _repository(tmp_path)
    timeline: list[str] = []
    audit = _Audit(timeline, fail_on=2)
    jail = _Jail(timeline)
    runner = EngineeringReproductionRunner(
        repo_root=repo,
        worktrees=WorktreeManager(repo, worktrees_dir=tmp_path / "worktrees"),
        audit=audit,
        jail=jail,
    )

    report = runner.reproduce(_request(candidate))

    assert report.status is ReproductionStatus.AUDIT_UNAVAILABLE
    assert report.execution_completed is True
    assert report.test_exit == 0
    assert report.audit_start_hash
    assert report.audit_result_hash is None
