"""
ADR-034 — Endurecimiento del subprocess de ejecución (Post-F hardening).

Verifica que process_hardening añade rlimits (FSIZE/NOFILE/NPROC además de
AS/CPU/CORE) + PR_SET_NO_NEW_PRIVS, y que LayeredIsolationSandbox los aplica:
los límites se hacen cumplir de verdad y el hijo corre en su propia sesión.
"""

from __future__ import annotations

import resource
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.security import process_hardening as ph
from atlas.security.sandbox import LayeredIsolationSandbox


# ===========================================================================
# Funciones puras
# ===========================================================================


def test_default_rlimits_includes_hardening_limits() -> None:
    rlimits = dict(ph.default_rlimits())
    # Los 3 previos + los nuevos.
    assert resource.RLIMIT_AS in rlimits
    assert resource.RLIMIT_CPU in rlimits
    assert resource.RLIMIT_CORE in rlimits
    assert rlimits[resource.RLIMIT_CORE] == (0, 0)
    assert resource.RLIMIT_FSIZE in rlimits
    assert resource.RLIMIT_NOFILE in rlimits
    if hasattr(resource, "RLIMIT_NPROC"):
        assert resource.RLIMIT_NPROC in rlimits


def test_default_rlimits_honors_overrides() -> None:
    rlimits = dict(ph.default_rlimits(fsize_bytes=123, nofile=7))
    assert rlimits[resource.RLIMIT_FSIZE] == (123, 123)
    assert rlimits[resource.RLIMIT_NOFILE] == (7, 7)


def test_nproc_none_omits_the_cap() -> None:
    # nproc=None omite RLIMIT_NPROC (servers MCP legítimos multihilo); el resto
    # del hardening permanece. RLIMIT_NPROC es por-usuario y un cap absoluto
    # mataría node/uv en un host con miles de hilos vivos.
    rlimits = dict(ph.default_rlimits(nproc=None))
    if hasattr(resource, "RLIMIT_NPROC"):
        assert resource.RLIMIT_NPROC not in rlimits
    # El resto del hardening sigue presente.
    assert resource.RLIMIT_AS in rlimits
    assert resource.RLIMIT_NOFILE in rlimits


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="prctl es Linux")
def test_set_no_new_privs_in_subprocess() -> None:
    """Aplicado en un subproceso aparte para no marcar irreversiblemente el
    proceso de pytest. Verifica retorno True y que el flag queda a 1."""
    code = (
        "from atlas.security.process_hardening import set_no_new_privs\n"
        "import ctypes\n"
        "ok = set_no_new_privs()\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "PR_GET_NO_NEW_PRIVS = 39\n"
        "flag = libc.prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0)\n"
        "print(f'{ok}:{flag}')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "True:1"


def test_hardening_never_raises_on_exotic_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si setrlimit y prctl fallan, apply_in_child degrada a no-op sin lanzar."""
    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("simulated unsupported platform")

    monkeypatch.setattr(ph.resource, "setrlimit", _boom)
    monkeypatch.setattr(ph, "set_no_new_privs", lambda: False)
    # No debe lanzar.
    ph.apply_in_child()


# ===========================================================================
# E2E vía sandbox
# ===========================================================================


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredIsolationSandbox:
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)
    return LayeredIsolationSandbox(workspace=tmp_path)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="rlimits POSIX")
def test_sandbox_enforces_fsize_limit(
    sandbox: LayeredIsolationSandbox, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escribir un archivo por encima de RLIMIT_FSIZE mata el proceso (SIGXFSZ)."""
    monkeypatch.setattr(sandbox, "FSIZE_LIMIT_NORMAL_BYTES", 1024 * 1024, raising=False)
    code = (
        "with open('big.bin','wb') as f:\n"
        "    f.write(b'x' * (8 * 1024 * 1024))\n"
        "print('SHOULD_NOT_REACH')\n"
    )
    result = sandbox.execute(code)
    assert result.success is False
    assert "SHOULD_NOT_REACH" not in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="setsid POSIX")
def test_sandbox_runs_in_new_session(sandbox: LayeredIsolationSandbox) -> None:
    """start_new_session=True → el hijo es líder de su sesión (getsid==pid).

    Se invoca _execute_normal directamente (la capa de subprocess que estamos
    probando): el AST Guard de execute() bloquea os.getsid/getpid, pero esa
    política es ortogonal al endurecimiento de proceso de ADR-034."""
    code = (
        "import os\n"
        "print('LEADER' if os.getpid() == os.getsid(0) else 'CHILD')\n"
    )
    result = sandbox._execute_normal(code, None)
    assert result.success is True, result.stderr
    assert "LEADER" in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="prctl/setsid son Linux/POSIX")
def test_sandbox_command_path_sets_no_new_privs_and_new_session(
    sandbox: LayeredIsolationSandbox,
) -> None:
    """execute_command() is the path used by AtlasExecutor for allowlisted
    commands; it must get the same child hardening as generated Python code."""
    code = (
        "import ctypes, os\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "PR_GET_NO_NEW_PRIVS = 39\n"
        "nnp = libc.prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0)\n"
        "leader = os.getpid() == os.getsid(0)\n"
        "print(f'nnp={nnp} leader={leader}')\n"
    )
    result = sandbox.execute_command(["python3", "-c", code])
    assert result.success is True, result.stderr
    assert "nnp=1" in result.stdout
    assert "leader=True" in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="rlimits POSIX")
def test_sandbox_command_path_enforces_fsize_limit(
    sandbox: LayeredIsolationSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The structured command path must not be able to fill the disk."""
    monkeypatch.setattr(sandbox, "FSIZE_LIMIT_NORMAL_BYTES", 1024 * 1024, raising=False)
    code = (
        "with open('big-command.bin','wb') as f:\n"
        "    f.write(b'x' * (8 * 1024 * 1024))\n"
        "print('SHOULD_NOT_REACH')\n"
    )
    result = sandbox.execute_command(["python3", "-c", code])
    assert result.success is False
    assert "SHOULD_NOT_REACH" not in result.stdout
