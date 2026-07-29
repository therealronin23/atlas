"""Tests for the jailed ColdUpdate validation boundary.

Never invoke a real full :class:`ValidationRunner` from pytest: inject a
recording jail and assert the bounded command/environment contract instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.security.bwrap_jail import BwrapUnavailableError


def _make_proc(returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = ""
    m.stderr = ""
    return m


@dataclass
class _JailCall:
    command: list[str]
    working_dir: Path
    working_dir_writable: bool
    read_only_paths: tuple[Path, ...]
    timeout_s: int
    extra_env: dict[str, str]


class _RecordingJail:
    def __init__(self) -> None:
        self.calls: list[_JailCall] = []
        self.CPU_TIME_LIMIT_S = 30
        self.RAM_LIMIT_BYTES = 512 * 1024 * 1024

    def run_command(
        self,
        command: list[str],
        *,
        working_dir: Path,
        working_dir_writable: bool,
        read_only_paths: tuple[Path, ...],
        timeout_s: int,
        extra_env: dict[str, str],
    ) -> MagicMock:
        self.calls.append(
            _JailCall(
                command=list(command),
                working_dir=working_dir,
                working_dir_writable=working_dir_writable,
                read_only_paths=read_only_paths,
                timeout_s=timeout_s,
                extra_env=dict(extra_env),
            )
        )
        return _make_proc(0)


def test_default_validation_uses_read_only_jail_without_host_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate tests execute in Bwrap with explicit, not inherited, env."""
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ATLAS_TEST_SECRET", "must-not-reach-candidate")
    jail = _RecordingJail()
    runner = ValidationRunner(
        tmp_path,
        extra_env={"ATLAS_HOME": "/candidate/home"},
        jail_factory=lambda: jail,
    )

    report = runner.run(timeout_s=17)

    assert report.passed is True
    assert len(jail.calls) == 2
    pytest_call, mypy_call = jail.calls
    assert pytest_call.command[:4] == [runner._python, "-m", "pytest", "tests/"]
    assert "-p" in pytest_call.command
    assert "no:cacheprovider" in pytest_call.command
    assert mypy_call.command == [runner._python, "-m", "mypy", "src/atlas/"]
    for call in jail.calls:
        assert call.working_dir == tmp_path.resolve()
        assert call.working_dir_writable is False
        assert call.timeout_s == 17
        assert call.extra_env["ATLAS_HOME"] == "/tmp/atlas-validation-home"
        assert str(tmp_path / "src") in call.extra_env["PYTHONPATH"]
        assert "ATLAS_TEST_SECRET" not in call.extra_env
        assert call.extra_env["HOME"] == "/tmp/atlas-validation-user"
        assert "PATH" not in call.extra_env


def test_jail_unavailable_fails_closed_before_candidate_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def _unavailable() -> _RecordingJail:
        raise BwrapUnavailableError("missing bwrap")

    runner = ValidationRunner(tmp_path, jail_factory=_unavailable)

    with pytest.raises(BwrapUnavailableError, match="missing bwrap"):
        runner.run(timeout_s=5)


def test_full_candidate_validation_gets_a_bounded_cpu_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full suite may outlive Bwrap's 30s command default, never its cap."""
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    jail = _RecordingJail()
    runner = ValidationRunner(tmp_path, jail_factory=lambda: jail)

    runner.run(timeout_s=600)

    assert jail.CPU_TIME_LIMIT_S == 120
    assert jail.RAM_LIMIT_BYTES == 14 * 1024 * 1024 * 1024


def test_linked_worktree_git_metadata_is_narrowly_read_only_mounted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git tests see their linked worktree metadata, never broad host state."""
    from atlas.core.validation_runner import ValidationRunner

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    common = tmp_path / "source" / ".git"
    git_dir = common / "worktrees" / "candidate"
    git_dir.mkdir(parents=True)
    (candidate / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    for name in ("objects", "refs", "info", "logs"):
        (common / name).mkdir(parents=True, exist_ok=True)
    (common / "packed-refs").write_text("", encoding="utf-8")
    (common / "config").write_text("[credential]\nhelper = unsafe\n", encoding="utf-8")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    jail = _RecordingJail()
    runner = ValidationRunner(candidate, jail_factory=lambda: jail)

    runner.run(timeout_s=5)

    paths = jail.calls[0].read_only_paths
    assert git_dir.resolve() in paths
    for name in ("objects", "refs", "info", "logs", "packed-refs"):
        assert (common / name).resolve() in paths
    assert (common / "config").resolve() not in paths
    assert jail.calls[0].extra_env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert jail.calls[0].extra_env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert jail.calls[0].extra_env["GIT_TERMINAL_PROMPT"] == "0"


def test_nonprotected_extra_env_reaches_the_jail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit non-protected controls survive without inheriting host env."""
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    jail = _RecordingJail()
    runner = ValidationRunner(
        tmp_path,
        extra_env={"ATLAS_VALIDATION_MARKER": "candidate-only"},
        jail_factory=lambda: jail,
    )

    runner.run(timeout_s=5)

    assert len(jail.calls) == 2
    for call in jail.calls:
        assert call.extra_env["ATLAS_VALIDATION_MARKER"] == "candidate-only"
        assert "PYTEST_CURRENT_TEST" not in call.extra_env


def test_protected_extra_env_is_remapped_away_from_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller cannot use extra_env to reintroduce host paths or loader state."""
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.setenv("ATLAS_HOME", "/original")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    jail = _RecordingJail()
    runner = ValidationRunner(
        tmp_path,
        extra_env={
            "ATLAS_HOME": "/overridden",
            "PATH": "/host/bin",
            "PYTHONPATH": "/host/site-packages",
            "LD_PRELOAD": "/host/evil.so",
        },
        jail_factory=lambda: jail,
    )

    runner.run(timeout_s=5)

    for call in jail.calls:
        assert call.extra_env["ATLAS_HOME"] == "/tmp/atlas-validation-home"
        assert str(tmp_path / "src") in call.extra_env["PYTHONPATH"]
        assert "/host/site-packages" not in call.extra_env["PYTHONPATH"]
        assert "PATH" not in call.extra_env
        assert "LD_PRELOAD" not in call.extra_env


def test_sin_extra_env_funciona(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """extra_env=None no rompe nada."""
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    jail = _RecordingJail()
    runner = ValidationRunner(tmp_path, jail_factory=lambda: jail)
    report = runner.run(timeout_s=5)

    assert report.passed is True
    assert len(jail.calls) == 2


def test_guard_antirecursion_lanza():
    """run() dentro de pytest (con PYTEST_CURRENT_TEST) debe levantar RuntimeError."""
    import os
    from atlas.core.validation_runner import ValidationRunner

    runner = ValidationRunner(Path("/tmp"))
    assert "PYTEST_CURRENT_TEST" in os.environ
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="recursiva"):
        runner.run()
