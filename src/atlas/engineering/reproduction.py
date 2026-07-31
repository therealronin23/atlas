"""Audited, fail-closed reproduction of a bounded test in an isolated worktree.

This is deliberately narrower than ColdUpdate: it never applies a patch,
starts a provider, creates a Task, or persists output.  It may execute only a
validated pytest target from an immutable commit, in a read-only ephemeral Git
worktree inside the existing networkless Bwrap jail.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from atlas.core.git_checkpoint import is_ephemeral_worktree
from atlas.core.git_env import clean_git_env
from atlas.core.validation_runner import ValidationReport
from atlas.security.bwrap_jail import BwrapJail, BwrapUnavailableError


class ReproductionStatus(str, Enum):
    """Outcome status; only PASSED has both execution and completion audit."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMED_OUT = "TIMED_OUT"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"


@dataclass(frozen=True)
class EngineeringReproductionRequest:
    """One bounded test reproduction against an immutable candidate commit."""

    run_id: str
    task_id: str | None
    mission_id: str | None
    repository: str
    base_revision: str
    candidate_revision: str
    correlation_id: str
    test_targets: tuple[str, ...]
    at: str
    timeout_s: int = 60


@dataclass(frozen=True)
class EngineeringReproductionReport:
    """In-memory outcome; callers must sanitize output before persistence."""

    request: EngineeringReproductionRequest
    status: ReproductionStatus
    command: tuple[str, ...]
    test_exit: int | None
    stdout: str
    stderr: str
    duration_ms: int | None
    execution_completed: bool
    audit_start_hash: str | None
    audit_result_hash: str | None
    reason: str = ""

    def to_validation_report(self) -> ValidationReport:
        """Expose an audited test capture to the existing diagnostic seam.

        The returned report is intentionally in-memory.  The diagnostic
        coordinator remains responsible for redacting and reducing it before
        anything becomes a persistent EngineeringFinding.
        """

        if (
            not self.execution_completed
            or self.audit_result_hash is None
            or self.status not in {ReproductionStatus.PASSED, ReproductionStatus.FAILED}
            or self.test_exit is None
        ):
            raise ValueError(
                "only an audited completed reproduction can become a validation capture"
            )
        pytest_summary = "\n".join(
            part for part in (self.stdout, self.stderr) if part
        )
        return ValidationReport(
            passed=self.status is ReproductionStatus.PASSED,
            pytest_exit=self.test_exit,
            mypy_exit=0,
            pytest_summary=pytest_summary,
            mypy_summary="",
            duration_s=round((self.duration_ms or 0) / 1000, 3),
            errors=[] if self.test_exit == 0 else ["pytest failed"],
        )


class _WorktreeManagerLike(Protocol):
    def session(
        self,
        name: str,
        *,
        base_ref: str = "HEAD",
    ) -> AbstractContextManager[Path]: ...


class _AuditRecordLike(Protocol):
    hash_self: str


class EngineeringReproductionAudit(Protocol):
    """The narrow audit seam required before any reproduction execution."""

    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> _AuditRecordLike: ...


class _JailResultLike(Protocol):
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class _CommandJailLike(Protocol):
    def run_command(
        self,
        command: tuple[str, ...],
        *,
        working_dir: Path,
        working_dir_writable: bool = False,
        read_only_paths: tuple[Path, ...] = (),
        timeout_s: int | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> _JailResultLike: ...


_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_TARGET_PATH = re.compile(r"^tests/[A-Za-z0-9_./-]+\.py$")
_TARGET_SELECTOR = re.compile(r"^[A-Za-z0-9_:\[\]-]+$")
_MAX_OUTPUT_CHARS = 4_000


class EngineeringReproductionRunner:
    """Run one restricted pytest command only after an audit record exists.

    The jail is constructed lazily so a missing Bwrap installation results in
    an explicit unavailable report rather than an unsafe local fallback.  A
    completion-audit failure also prevents a successful execution from being
    presented as an accepted reproduction.
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        worktrees: _WorktreeManagerLike,
        audit: EngineeringReproductionAudit,
        jail: _CommandJailLike | None = None,
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._worktrees = worktrees
        self._audit = audit
        self._jail = jail

    def reproduce(self, request: EngineeringReproductionRequest) -> EngineeringReproductionReport:
        """Execute a validated target in Bwrap, or return an explicit non-success."""

        try:
            command = self._validate_and_build_command(request)
            self._verify_commit(request.base_revision, "base revision")
            self._verify_commit(request.candidate_revision, "candidate revision")
        except ValueError as exc:
            return self._report(
                request,
                status=ReproductionStatus.REJECTED,
                command=(),
                reason=str(exc),
            )
        except (OSError, subprocess.TimeoutExpired):
            return self._report(
                request,
                status=ReproductionStatus.UNAVAILABLE,
                command=command,
                reason="candidate commit could not be verified",
            )

        start = self._start_audit(request, command)
        if start is None:
            return self._report(
                request,
                status=ReproductionStatus.AUDIT_UNAVAILABLE,
                command=command,
                reason="audit unavailable before reproduction",
            )

        try:
            jail = self._jail or BwrapJail()
        except BwrapUnavailableError:
            return self._finish_audit(
                self._report(
                    request,
                    status=ReproductionStatus.UNAVAILABLE,
                    command=command,
                    audit_start_hash=start.hash_self,
                    reason="isolated jail unavailable",
                )
            )

        try:
            with self._worktrees.session(
                self._worktree_name(request),
                base_ref=request.candidate_revision,
            ) as worktree:
                self._verify_ephemeral_worktree(worktree)
                result = jail.run_command(
                    command,
                    working_dir=worktree,
                    working_dir_writable=False,
                    read_only_paths=self._runtime_paths(),
                    timeout_s=request.timeout_s,
                    extra_env=self._jail_environment(worktree),
                )
        except BwrapUnavailableError:
            return self._finish_audit(
                self._report(
                    request,
                    status=ReproductionStatus.UNAVAILABLE,
                    command=command,
                    audit_start_hash=start.hash_self,
                    reason="isolated jail unavailable",
                )
            )
        except subprocess.TimeoutExpired:
            return self._finish_audit(
                self._report(
                    request,
                    status=ReproductionStatus.TIMED_OUT,
                    command=command,
                    audit_start_hash=start.hash_self,
                    reason="isolated reproduction timed out",
                )
            )
        except (OSError, RuntimeError, ValueError):
            return self._finish_audit(
                self._report(
                    request,
                    status=ReproductionStatus.UNAVAILABLE,
                    command=command,
                    audit_start_hash=start.hash_self,
                    reason="isolated reproduction could not be started",
                )
            )

        report = self._report(
            request,
            status=(ReproductionStatus.PASSED if result.returncode == 0 else ReproductionStatus.FAILED),
            command=command,
            test_exit=result.returncode,
            stdout=_bounded_output(result.stdout),
            stderr=_bounded_output(result.stderr),
            duration_ms=result.duration_ms,
            execution_completed=True,
            audit_start_hash=start.hash_self,
        )
        return self._finish_audit(report)

    def _validate_and_build_command(
        self,
        request: EngineeringReproductionRequest,
    ) -> tuple[str, ...]:
        if not self._repo_root.is_dir():
            raise ValueError("reproduction repository root is unavailable")
        for name, value in (
            ("run_id", request.run_id),
            ("repository", request.repository),
            ("correlation_id", request.correlation_id),
        ):
            if not _SAFE_ID.fullmatch(value):
                raise ValueError(f"{name} must be a safe opaque identifier")
        if not request.at.strip():
            raise ValueError("reproduction timestamp is required")
        if not _COMMIT_SHA.fullmatch(request.base_revision):
            raise ValueError("base revision must be a full immutable commit SHA")
        if not _COMMIT_SHA.fullmatch(request.candidate_revision):
            raise ValueError("candidate revision must be a full immutable commit SHA")
        if not 1 <= request.timeout_s <= 300:
            raise ValueError("reproduction timeout must be between 1 and 300 seconds")
        if not 1 <= len(request.test_targets) <= 16:
            raise ValueError("reproduction requires between 1 and 16 test targets")
        targets = tuple(self._validate_target(target) for target in request.test_targets)
        return (
            # SIN `.resolve()`: en un venv, `bin/python` es un symlink al
            # intérprete del sistema y seguirlo SE SALE del virtualenv --
            # `_runtime_paths()` monta `sys.prefix` (donde vive pytest) pero
            # el intérprete resuelto ya no lo mira. Medido el 2026-07-31 con
            # una corrida real: reproducir un test que pasa daba FAILED en
            # 64 ms con "No module named pytest". El peor fallo posible para
            # un reproductor: no dice "no puedo", dice FAILED con confianza.
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
            *targets,
        )

    @staticmethod
    def _validate_target(target: str) -> str:
        path, separator, selector = target.partition("::")
        if not _TARGET_PATH.fullmatch(path):
            raise ValueError("reproduction target must be a relative tests/*.py path")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("reproduction target may not escape tests/")
        if separator and not _TARGET_SELECTOR.fullmatch(selector):
            raise ValueError("reproduction selector contains unsupported characters")
        return target

    def _verify_commit(self, revision: str, label: str) -> None:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
            cwd=self._repo_root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(f"{label} does not resolve to a commit")

    def _verify_ephemeral_worktree(self, worktree: Path) -> None:
        if not is_ephemeral_worktree(worktree):
            raise RuntimeError("reproduction runner requires an ephemeral Git worktree")
        if self._git_common_dir(worktree) != self._git_common_dir(self._repo_root):
            raise RuntimeError("reproduction worktree is outside the governed repository")

    @staticmethod
    def _git_common_dir(directory: Path) -> Path:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=directory,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("Git could not prove the worktree common directory")
        raw = Path(result.stdout.strip())
        return (raw if raw.is_absolute() else directory / raw).resolve()

    @staticmethod
    def _worktree_name(request: EngineeringReproductionRequest) -> str:
        fingerprint = hashlib.sha256(
            f"{request.correlation_id}\x00{request.candidate_revision}".encode("utf-8")
        ).hexdigest()[:16]
        return f"engineering-reproduction-{fingerprint}"

    @staticmethod
    def _runtime_paths() -> tuple[Path, ...]:
        prefix = Path(sys.prefix).resolve()
        base_prefix = Path(sys.base_prefix).resolve()
        return tuple(path for path in (prefix, base_prefix) if path != Path("/usr"))

    @staticmethod
    def _jail_environment(worktree: Path) -> dict[str, str]:
        return {
            "PYTHONPATH": str(worktree / "src"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "ATLAS_MEMORY_VECTOR": "0",
            "ATLAS_NESTED_TEST_RUN": "1",
            "HF_HUB_OFFLINE": "1",
        }

    def _start_audit(
        self,
        request: EngineeringReproductionRequest,
        command: tuple[str, ...],
    ) -> _AuditRecordLike | None:
        try:
            return self._audit.log(
                action="engineering.reproduction.started",
                agent="engineering.reproduction_runner",
                result="pending",
                risk_level="high",
                payload=self._audit_payload(request, command),
                task_id=request.task_id,
            )
        except Exception:  # noqa: BLE001 - no audit means no execution
            return None

    def _finish_audit(
        self,
        report: EngineeringReproductionReport,
    ) -> EngineeringReproductionReport:
        try:
            record = self._audit.log(
                action="engineering.reproduction.completed",
                agent="engineering.reproduction_runner",
                result=self._audit_result(report.status),
                risk_level="high",
                payload={
                    **self._audit_payload(report.request, report.command),
                    "status": report.status.value,
                    "test_exit": report.test_exit,
                    "duration_ms": report.duration_ms,
                    "execution_completed": report.execution_completed,
                },
                task_id=report.request.task_id,
            )
        except Exception:  # noqa: BLE001 - execution outcome is not promotable without receipt
            return replace(
                report,
                status=ReproductionStatus.AUDIT_UNAVAILABLE,
                audit_result_hash=None,
                reason="completion audit unavailable; execution outcome is not promotable",
            )
        return replace(report, audit_result_hash=record.hash_self)

    @staticmethod
    def _audit_payload(
        request: EngineeringReproductionRequest,
        command: tuple[str, ...],
    ) -> dict[str, object]:
        target_fingerprint = hashlib.sha256(
            "\x00".join(request.test_targets).encode("utf-8")
        ).hexdigest()
        return {
            "run_id": request.run_id,
            "repository": request.repository,
            "base_revision": request.base_revision,
            "candidate_revision": request.candidate_revision,
            "correlation_id": request.correlation_id,
            "target_count": len(request.test_targets),
            "target_fingerprint": f"sha256:{target_fingerprint}",
            "command_kind": "pytest",
            "command_arg_count": len(command),
        }

    @staticmethod
    def _audit_result(status: ReproductionStatus) -> str:
        if status is ReproductionStatus.PASSED:
            return "success"
        if status in {ReproductionStatus.FAILED, ReproductionStatus.TIMED_OUT}:
            return "failure"
        return "blocked"

    @staticmethod
    def _report(
        request: EngineeringReproductionRequest,
        *,
        status: ReproductionStatus,
        command: tuple[str, ...],
        test_exit: int | None = None,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int | None = None,
        execution_completed: bool = False,
        audit_start_hash: str | None = None,
        reason: str = "",
    ) -> EngineeringReproductionReport:
        return EngineeringReproductionReport(
            request=request,
            status=status,
            command=command,
            test_exit=test_exit,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            execution_completed=execution_completed,
            audit_start_hash=audit_start_hash,
            audit_result_hash=None,
            reason=reason,
        )


def _bounded_output(output: str) -> str:
    """Keep runtime-only output bounded; persistence remains caller-owned."""

    return output[-_MAX_OUTPUT_CHARS:]
