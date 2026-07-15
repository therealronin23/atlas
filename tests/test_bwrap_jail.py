"""Tests for ADR-055 Slice 1 — BwrapJail + Slice 3 (executor wiring).

La mayoría de los tests mockean subprocess. Los tests marcados con
pytestmark_bwrap requieren bwrap instalado y ejecutan el jail real (sin mocks)
para verificar el rootfs mínimo y el seccomp BPF activo.
"""
from __future__ import annotations

import shutil
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.security.bwrap_jail import (
    _BLOCKED_X86_64,
    BwrapJail,
    BwrapResult,
    BwrapUnavailableError,
    _find_bwrap,
    _require_bwrap,
    build_bwrap_argv,
    build_command_bwrap_argv,
    build_seccomp_bpf,
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


def test_bwrap_argv_ro_binds_usr_not_root():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    # Rootfs mínimo: debe montar /usr read-only, NO / completo
    assert "--ro-bind" in argv
    ro_bind_pairs = [
        (argv[i + 1], argv[i + 2])
        for i in range(len(argv) - 2)
        if argv[i] == "--ro-bind"
    ]
    sources = [src for src, _dst in ro_bind_pairs]
    assert "/usr" in sources, "--ro-bind /usr /usr debe aparecer"
    assert "/" not in sources, "--ro-bind / / NO debe aparecer (exfiltración de secretos)"


def test_bwrap_argv_home_not_mounted():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    # Ningún argumento debe referenciar el home del host
    import os
    host_home = os.path.expanduser("~")
    assert host_home not in argv, f"$HOME del host ({host_home}) no debe aparecer en el argv del jail"


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


def test_command_bwrap_argv_mounts_only_working_dir(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    argv = build_command_bwrap_argv(
        "/usr/bin/bwrap", ["git", "status"], str(work),
    )
    bind_pairs = [
        (argv[i + 1], argv[i + 2])
        for i in range(len(argv) - 2)
        if argv[i] in {"--bind", "--ro-bind"}
    ]
    assert (str(work), str(work)) in bind_pairs
    assert ("/", "/") not in bind_pairs
    assert argv[argv.index("--chdir") + 1] == str(work)
    assert argv[-2:] == ["git", "status"]


def test_command_bwrap_argv_defaults_working_dir_to_read_only(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    argv = build_command_bwrap_argv(
        "/usr/bin/bwrap", ["find", "."], str(work),
    )
    ro_pairs = [
        (argv[i + 1], argv[i + 2])
        for i in range(len(argv) - 2)
        if argv[i] == "--ro-bind"
    ]
    assert (str(work), str(work)) in ro_pairs


def test_command_bwrap_argv_can_mount_explicit_read_only_input(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    input_file = tmp_path / "change.patch"
    input_file.write_text("diff", encoding="utf-8")
    argv = build_command_bwrap_argv(
        "/usr/bin/bwrap",
        ["patch", "--input", str(input_file)],
        str(work),
        working_dir_writable=True,
        read_only_paths=(str(input_file),),
    )
    bind_pairs = [
        (argv[i + 1], argv[i + 2])
        for i in range(len(argv) - 2)
        if argv[i] in {"--bind", "--ro-bind"}
    ]
    assert (str(work), str(work)) in bind_pairs
    assert (str(input_file), str(input_file)) in bind_pairs


def test_command_bwrap_argv_rejects_empty_command(tmp_path: Path):
    with pytest.raises(ValueError, match="vacio"):
        build_command_bwrap_argv("/usr/bin/bwrap", [], str(tmp_path))


# ---------------------------------------------------------------------------
# Slice 2 — cap-drop + seccomp BPF (tests puros, sin lanzar bwrap)
# ---------------------------------------------------------------------------


def test_bwrap_argv_cap_drop_all():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--cap-drop" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"


def test_bwrap_argv_seccomp_fd_present_when_given():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out", seccomp_fd=7)
    assert "--seccomp" in argv
    assert argv[argv.index("--seccomp") + 1] == "7"


def test_bwrap_argv_no_seccomp_when_none():
    argv = build_bwrap_argv("/usr/bin/bwrap", "/tmp/s.py", "/tmp/out")
    assert "--seccomp" not in argv


def test_seccomp_bpf_structure():
    bpf = build_seccomp_bpf()
    # Cada filtro son 8 bytes; nº instrucciones = 4 + M bloqueadas + 2 (allow/errno).
    m = len(_BLOCKED_X86_64)
    assert len(bpf) == (4 + m + 2) * 8
    filters = [struct.unpack("<HBBI", bpf[i:i + 8]) for i in range(0, len(bpf), 8)]
    # [0] load arch (offset 4); [1] JEQ arch; última es RET ERRNO EPERM.
    assert filters[0] == (0x20, 0, 0, 4)
    assert filters[1][0] == 0x15 and filters[1][3] == 0xC000003E
    assert filters[-1] == (0x06, 0, 0, 0x00050001)   # RET ERRNO|EPERM
    assert filters[-2] == (0x06, 0, 0, 0x7FFF0000)   # RET ALLOW (default)
    # Cada syscall bloqueada aparece como JEQ con k == nr.
    blocked_ks = {f[3] for f in filters if f[0] == 0x15 and f[3] != 0xC000003E}
    assert set(_BLOCKED_X86_64) <= blocked_ks


def test_seccomp_bpf_deterministic():
    assert build_seccomp_bpf() == build_seccomp_bpf()


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


def test_bwrap_jail_run_command_uses_jail_and_devnull_stdin(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        jail = BwrapJail()
    with patch("subprocess.run", return_value=_make_proc()) as mock_run:
        result = jail.run_command(["echo", "ok"], working_dir=work)
    argv = mock_run.call_args.args[0]
    kwargs = mock_run.call_args.kwargs
    assert result.success is True
    assert "--unshare-all" in argv
    assert argv[-2:] == ["echo", "ok"]
    assert kwargs["stdin"] is not None


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


# ---------------------------------------------------------------------------
# Tests de ejecución real en el jail (bwrap instalado, x86_64)
# Estos tests NO mockean subprocess — ejercitan el jail real.
# ---------------------------------------------------------------------------

_bwrap_available = shutil.which("bwrap") is not None
pytestmark_bwrap = pytest.mark.skipif(
    not _bwrap_available, reason="bwrap no disponible en este entorno"
)


@pytest.fixture(scope="module")
def real_jail() -> BwrapJail:
    """BwrapJail real (no mockeada) para tests de integración."""
    return BwrapJail()


@pytestmark_bwrap
def test_real_jail_basic_python(real_jail: BwrapJail) -> None:
    """Python básico funciona dentro del jail mínimo."""
    result = real_jail.run("print(2 + 2)")
    assert result.success, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "4"


@pytestmark_bwrap
def test_real_jail_cannot_read_ssh_dir(real_jail: BwrapJail) -> None:
    """El jail no puede listar ~/.ssh — no está montado (canal de exfiltración cerrado)."""
    script = """
import os, sys
ssh_dir = os.path.join(os.path.expanduser('~'), '.ssh')
try:
    os.listdir(ssh_dir)
    print('FAIL: ssh dir accesible', file=sys.stderr)
    sys.exit(1)
except (FileNotFoundError, PermissionError):
    print('ok: ssh dir no accesible')
"""
    result = real_jail.run(script)
    assert result.success, f"stderr: {result.stderr}"
    assert "ok" in result.stdout


@pytestmark_bwrap
def test_real_jail_cannot_read_dotenv(real_jail: BwrapJail) -> None:
    """El jail no puede leer el .env del repo (canal de exfiltración cerrado)."""
    import os as _os
    repo_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    dotenv_path = _os.path.join(repo_root, ".env")
    script = f"""
import sys
try:
    with open({dotenv_path!r}) as f:
        f.read()
    print('FAIL: .env accesible', file=sys.stderr)
    sys.exit(1)
except (FileNotFoundError, PermissionError):
    print('ok: .env no accesible')
"""
    result = real_jail.run(script)
    assert result.success, f"stderr: {result.stderr}"
    assert "ok" in result.stdout


@pytestmark_bwrap
def test_real_jail_ptrace_blocked_eperm(real_jail: BwrapJail) -> None:
    """ptrace (nr=101) retorna EPERM — el BPF blocklist no está degradado a allow-all."""
    import platform
    if platform.machine() != "x86_64":
        pytest.skip("seccomp blocklist solo en x86_64")

    script = """
import ctypes, errno, sys
PTRACE_TRACEME = 0
libc = ctypes.CDLL(None, use_errno=True)
libc.ptrace.restype = ctypes.c_long
libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
ret = libc.ptrace(PTRACE_TRACEME, 0, None, None)
err = ctypes.get_errno()
if err == errno.EPERM:
    print('ok: ptrace bloqueado EPERM')
else:
    print(f'FAIL: ret={ret} errno={err} (esperado EPERM=1)', file=sys.stderr)
    sys.exit(1)
"""
    result = real_jail.run(script)
    assert result.success, f"stderr: {result.stderr}"
    assert "ok" in result.stdout


@pytestmark_bwrap
def test_real_command_jail_reads_cwd_but_not_host_parent(
    real_jail: BwrapJail, tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "visible.txt").write_text("VISIBLE", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("HOST_SECRET", encoding="utf-8")

    visible = real_jail.run_command(["cat", "visible.txt"], working_dir=work)
    blocked = real_jail.run_command(["cat", str(secret)], working_dir=work)

    assert visible.success and visible.stdout.strip() == "VISIBLE"
    assert blocked.success is False
    assert "HOST_SECRET" not in blocked.stdout


@pytestmark_bwrap
def test_real_command_jail_working_dir_is_read_only_by_default(
    real_jail: BwrapJail, tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = real_jail.run_command(
        ["python3", "-c", "open('escape.txt','w').write('x')"],
        working_dir=work,
    )
    assert result.success is False
    assert not (work / "escape.txt").exists()


@pytestmark_bwrap
def test_real_command_jail_explicit_writable_working_dir(
    real_jail: BwrapJail, tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = real_jail.run_command(
        ["python3", "-c", "open('result.txt','w').write('ok')"],
        working_dir=work,
        working_dir_writable=True,
    )
    assert result.success, result.stderr
    assert (work / "result.txt").read_text(encoding="utf-8") == "ok"


@pytestmark_bwrap
def test_real_command_jail_has_no_network(real_jail: BwrapJail, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    code = (
        "import socket; "
        "socket.create_connection(('1.1.1.1', 53), timeout=0.2)"
    )
    result = real_jail.run_command(["python3", "-c", code], working_dir=work)
    assert result.success is False


def test_new_lpe_syscalls_in_blocklist() -> None:
    """io_uring (425-427), userfaultfd (323) y clone3 (435) están en _BLOCKED_X86_64."""
    new_syscalls = {323, 425, 426, 427, 435}
    assert new_syscalls <= set(_BLOCKED_X86_64), (
        f"Faltan syscalls en el blocklist: {new_syscalls - set(_BLOCKED_X86_64)}"
    )
