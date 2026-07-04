"""Tests for atlas.core.lesson_runner."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from atlas.core.lesson_runner import LessonRunner, WorktreeError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_FAKE_TMPDIR = "/tmp/fake_lesson_tmp"
_WT_BEFORE = _FAKE_TMPDIR + "/before"
_WT_AFTER = _FAKE_TMPDIR + "/after"


def _make_fake_run(before_rc: int, after_rc: int):
    """Return a side_effect callable that simulates git + pytest calls."""
    call_count: dict[str, int] = {"pytest": 0}

    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "worktree", "add"]:
            return MagicMock(returncode=0, stderr=b"")
        if cmd[:3] == ["git", "worktree", "remove"]:
            return MagicMock(returncode=0)
        if cmd[0] == "pytest":
            call_count["pytest"] += 1
            rc = before_rc if call_count["pytest"] == 1 else after_rc
            return MagicMock(returncode=rc)
        return MagicMock(returncode=0)

    return fake_run


# ---------------------------------------------------------------------------
# fixtures / shared patches context
# ---------------------------------------------------------------------------

def _run_lesson(fake_run_side_effect):
    """Run LessonRunner.run with all external side-effects mocked."""
    runner = LessonRunner(repo_root=None)
    with patch("atlas.core.lesson_runner.tempfile.mkdtemp", return_value=_FAKE_TMPDIR), \
         patch("atlas.core.lesson_runner.BwrapJail.is_available", return_value=False), \
         patch("atlas.core.lesson_runner.subprocess.run", side_effect=fake_run_side_effect) as mock_sub:
        result = runner.run("tests/test_foo.py", "abc123")
    return result, mock_sub


# ---------------------------------------------------------------------------
# test 1 — red/green: failed_before=True, passes_after=True
# ---------------------------------------------------------------------------

def test_run_returns_prove_it_result_red_green():
    result, _ = _run_lesson(_make_fake_run(before_rc=1, after_rc=0))
    assert result.failed_before is True
    assert result.passes_after is True
    assert result.fix_commit == "abc123"
    assert result.test_path == "tests/test_foo.py"


# ---------------------------------------------------------------------------
# test 2 — failed_before=False when test passes before
# ---------------------------------------------------------------------------

def test_run_failed_before_false_when_test_passes_before():
    result, _ = _run_lesson(_make_fake_run(before_rc=0, after_rc=0))
    assert result.failed_before is False


# ---------------------------------------------------------------------------
# test 3 — passes_after=False when test fails after
# ---------------------------------------------------------------------------

def test_run_passes_after_false_when_test_fails_after():
    result, _ = _run_lesson(_make_fake_run(before_rc=1, after_rc=1))
    assert result.passes_after is False


# ---------------------------------------------------------------------------
# test 4 — WorktreeError when git worktree add fails
# ---------------------------------------------------------------------------

def test_worktree_error_on_git_failure():
    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "worktree", "add"]:
            return MagicMock(returncode=1, stderr=b"fatal: already exists")
        return MagicMock(returncode=0)

    runner = LessonRunner(repo_root=None)
    with patch("atlas.core.lesson_runner.tempfile.mkdtemp", return_value=_FAKE_TMPDIR), \
         patch("atlas.core.lesson_runner.BwrapJail.is_available", return_value=False), \
         patch("atlas.core.lesson_runner.subprocess.run", side_effect=fake_run):
        with pytest.raises(WorktreeError):
            runner.run("tests/test_foo.py", "abc123")


# ---------------------------------------------------------------------------
# test 5 — cleanup (git worktree remove) runs even when pytest raises
# ---------------------------------------------------------------------------

def test_cleanup_runs_on_pytest_failure():
    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "worktree", "add"]:
            return MagicMock(returncode=0, stderr=b"")
        if cmd[:3] == ["git", "worktree", "remove"]:
            return MagicMock(returncode=0)
        if cmd[0] == "pytest":
            raise Exception("pytest exploded")
        return MagicMock(returncode=0)

    runner = LessonRunner(repo_root=None)
    with patch("atlas.core.lesson_runner.tempfile.mkdtemp", return_value=_FAKE_TMPDIR), \
         patch("atlas.core.lesson_runner.BwrapJail.is_available", return_value=False), \
         patch("atlas.core.lesson_runner.subprocess.run", side_effect=fake_run) as mock_sub:
        with pytest.raises(Exception, match="pytest exploded"):
            runner.run("tests/test_foo.py", "abc123")

    remove_calls = [
        c for c in mock_sub.call_args_list
        if c.args and c.args[0][:3] == ["git", "worktree", "remove"]
    ]
    assert len(remove_calls) >= 1, "git worktree remove debe llamarse al limpiar"
