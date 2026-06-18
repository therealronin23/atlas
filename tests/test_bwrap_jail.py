"""Tests for ADR-055 Slice 1 — BwrapJail + Slice 3 (executor wiring).

Mocks subprocess entirely — no real processes launched (per project convention).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.security.bwrap_jail import (
    BwrapJail,
    BwrapResult,
    BwrapUnavailableError,
    _find_bwrap,
    _require_bwrap,
    build_bwrap_argv,
)


# ---------------------------------------------------------------------------
# _find_bwrap / _require_bwrap
# ---------------------------------------------------------------------------


def test_find_bwrap_returns_path_when_available():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        assert _find_bwrap() == "/usr/bin/bwrap"


def test_find_bwrap_returns_none_when_missing():
    with patch("shutil.which", return_value=None):
        assert _find_bwrap() is None


def test_require_bwrap_raises_when_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(BwrapUnavailableError):
            _require_bwrap()


def test_require_bwrap_returns_path_when_available():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        assert _require_bwrap() == "/usr/bin/bwrap"


# ---------------------------------------------------------------------------
# build_bwrap_argv
# ---------------------------------------------------------------------------


def test_bwrap_argv_starts_with_bwrap_bin():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert argv[0] == "/usr/bin/bwrap"


def test_bwrap_argv_contains_unshare_all():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--unshare-all" in argv


def test_bwrap_argv_maps_nobody_uid_gid():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--uid" in argv and "--gid" in argv
    uid_idx = argv.index("--uid")
    gid_idx = argv.index("--gid")
    assert argv[uid_idx + 1] == "65534"
    assert argv[gid_idx + 1] == "65534"


def test_bwrap_argv_ro_binds_root():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    # --ro-bind / / must appear
    assert "--ro-bind" in argv
    idx = argv.index("--ro-bind")
    assert argv[idx + 1] == "/" and argv[idx + 2] == "/"


def test_bwrap_argv_tmpfs_on_tmp():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--tmpfs" in argv
    idx = argv.index("--tmpfs")
    assert argv[idx + 1] == "/tmp"


def test_bwrap_argv_die_with_parent():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--die-with-parent" in argv


def test_bwrap_argv_new_session():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--new-session" in argv


def test_bwrap_argv_ends_with_python_and_script():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert argv[-2] == "python3"
    assert argv[-1] == "/tmp/atlas_script.py"


def test_bwrap_argv_custom_python_bin():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out", python_bin="/usr/bin/python3.11")
    assert argv[-2] == "/usr/bin/python3.11"


def test_bwrap_argv_binds_output_dir():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    # --bind <output_dir> /tmp/atlas_output
    assert "--bind" in argv
    idx = argv.index("--bind")
    assert argv[idx + 1] == "/tmp/out"
    assert argv[idx + 2] == "/tmp/atlas_output"


# ---------------------------------------------------------------------------
# BwrapJail constructor
# ---------------------------------------------------------------------------


def test_bwrap_jail_raises_on_construction_if_unavailable():
    with patch("shutil.which", return_value=None):
        with pytest.raises(BwrapUnavailableError):
            BwrapJail()


def test_bwrap_jail_is_available_false_when_missing():
    with patch("shutil.which", return_value=None):
        assert BwrapJail.is_available() is False


def test_bwrap_jail_is_available_true_when_present():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        assert BwrapJail.is_available() is True


# ---------------------------------------------------------------------------
# BwrapJail.run — mocked subprocess
# ---------------------------------------------------------------------------


def _make_proc(returncode=0, stdout="ok\n", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def test_bwrap_jail_run_returns_bwrap_result():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        result = jail.run("print('hello')")
    assert isinstance(result, BwrapResult)
    assert result.success is True
    assert result.stdout == "ok\n"
    mock_run.assert_called_once()


def test_bwrap_jail_run_captures_nonzero_exit():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc(returncode=1, stdout="", stderr="err")):
        result = jail.run("raise Exception()")
    assert result.success is False
    assert result.returncode == 1
    assert result.stderr == "err"


def test_bwrap_jail_run_passes_timeout():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        jail.run("x=1", timeout_s=5)
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 5


def test_bwrap_jail_run_uses_default_timeout_when_not_specified():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        jail.run("x=1")
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == BwrapJail.WALL_TIMEOUT_S


def test_bwrap_jail_run_argv_contains_bwrap():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        jail.run("x=1")
    argv = mock_run.call_args[0][0]
    assert argv[0] == "/usr/bin/bwrap"


def test_bwrap_jail_run_env_is_restricted():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        jail.run("x=1")
    _, kwargs = mock_run.call_args
    env = kwargs["env"]
    # Must not leak host env variables like HOME pointing to /root
    assert env["HOME"] == "/tmp"
    assert "PYTHONDONTWRITEBYTECODE" in env


def test_bwrap_jail_run_extra_env_merged():
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        jail.run("x=1", extra_env={"MY_VAR": "1"})
    _, kwargs = mock_run.call_args
    assert kwargs["env"]["MY_VAR"] == "1"


# ---------------------------------------------------------------------------
# Sandbox.execute_in_jail
# ---------------------------------------------------------------------------


def test_execute_in_jail_fail_closed_without_bwrap():
    from atlas.security.sandbox import LayeredIsolationSandbox

    sandbox = LayeredIsolationSandbox(Path("/tmp"))
    # Patch _get_bwrap to return None (bwrap unavailable)
    sandbox._bwrap = None  # force-set cache
    with pytest.raises(BwrapUnavailableError):
        sandbox.execute_in_jail("print('x')")


def test_execute_in_jail_ast_guard_lint_rejects_blocked_code():
    """AST Guard pre-lint still rejects obvious violations (defense-in-depth)."""
    from atlas.security.sandbox import LayeredIsolationSandbox
    from atlas.security.bwrap_jail import BwrapJail

    sandbox = LayeredIsolationSandbox(Path("/tmp"))
    mock_jail = MagicMock(spec=BwrapJail)
    sandbox._bwrap = mock_jail

    # Code that AST Guard lint should flag (__import__ is in BLOCKED_CALLS)
    result = sandbox.execute_in_jail("__import__('os')")
    assert result.success is False
    assert "AST Guard" in result.stderr
    mock_jail.run.assert_not_called()


def test_execute_in_jail_clean_code_calls_jail_run():
    from atlas.security.sandbox import LayeredIsolationSandbox
    from atlas.security.bwrap_jail import BwrapJail, BwrapResult

    sandbox = LayeredIsolationSandbox(Path("/tmp"))
    mock_jail = MagicMock(spec=BwrapJail)
    mock_jail.run.return_value = BwrapResult(
        returncode=0, stdout="42\n", stderr="", duration_ms=5
    )
    sandbox._bwrap = mock_jail

    result = sandbox.execute_in_jail("print(6 * 7)")
    assert result.success is True
    assert result.stdout == "42\n"
    mock_jail.run.assert_called_once()
