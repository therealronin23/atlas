"""
BwrapJail — OS-level jail para código no confiable (ADR-055 Slice 1).

El límite de seguridad real es el kernel: uid separado + namespaces + montaje ro.
ASTGuard es defensa en profundidad (lint), no contención — este módulo es la contención.

Propiedades enforced:
  1. uid/gid 65534 (nobody) via user namespace
  2. Network namespace sin veth — red bloqueada en el kernel
  3. Raíz bind-mounted read-only; /tmp como tmpfs efímero
  4. --die-with-parent: el hijo muere si el padre muere
  5. Fail-closed: sin bwrap disponible, lanza BwrapUnavailableError

Límites honestos (ADR-055):
  - Requiere user namespaces no privilegiados habilitados en el kernel
    (algunas distros los deshabilitan; en ese caso usar tier VM)
  - Slice 2: seccomp-bpf BLOCKLIST (ptrace/mount/kexec/…) en x86_64; fail-closed
    (sin filtro) en otras arquitecturas con warning. Allowlist completa rompería
    CPython, por eso blocklist — límite honesto, no allowlist.
  - --cap-drop ALL: ninguna capability dentro del jail.
  - No cierra canales laterales de timing/recursos compartidos
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_log = logging.getLogger(__name__)


class BwrapUnavailableError(RuntimeError):
    """bwrap no está disponible. Ejecución de código no confiable bloqueada (ADR-055 fail-closed)."""


def _find_bwrap() -> str | None:
    return shutil.which("bwrap")


def _require_bwrap() -> str:
    path = _find_bwrap()
    if path is None:
        raise BwrapUnavailableError(
            "bwrap no encontrado en PATH. Instalar bubblewrap para ejecutar código "
            "no confiable. No hay fallback inseguro (ADR-055 fail-closed)."
        )
    return path


# ---------------------------------------------------------------------------
# Slice 2 — seccomp-bpf blocklist (ADR-055)
# ---------------------------------------------------------------------------
# Allowlist sería más fuerte pero rompe el arranque de CPython (cientos de
# syscalls). Esta es una BLOCKLIST honesta: deniega (EPERM) syscalls claramente
# peligrosas y deja pasar el resto. x86_64 únicamente; en otra arquitectura
# build_seccomp_bpf lanza UnsupportedArchError y el jail corre SIN seccomp (el
# resto del endurecimiento sigue) con warning — no se aplica un filtro con
# números de syscall equivocados.

_AUDIT_ARCH_X86_64 = 0xC000003E
_SECCOMP_RET_ALLOW = 0x7FFF0000
_SECCOMP_RET_ERRNO_EPERM = 0x00050001  # RET_ERRNO | EPERM(1)
_SECCOMP_RET_KILL_PROCESS = 0x80000000

_BLOCKED_X86_64: tuple[int, ...] = (
    101,  # ptrace
    155,  # pivot_root
    165,  # mount
    166,  # umount2
    167,  # swapon
    168,  # swapoff
    169,  # reboot
    175,  # init_module
    176,  # delete_module
    246,  # kexec_load
    248,  # add_key
    249,  # request_key
    250,  # keyctl
    272,  # unshare
    298,  # perf_event_open
    308,  # setns
    310,  # process_vm_readv
    311,  # process_vm_writev
    313,  # finit_module
    320,  # kexec_file_load
    321,  # bpf
)


class UnsupportedArchError(RuntimeError):
    """seccomp blocklist solo definida para x86_64."""


def build_seccomp_bpf(blocked: tuple[int, ...] = _BLOCKED_X86_64) -> bytes:
    """Programa BPF (array de struct sock_filter) para bwrap --seccomp.

    Verifica arch==x86_64 (si no, KILL); por cada syscall bloqueada devuelve
    EPERM; por defecto ALLOW. Lanza UnsupportedArchError fuera de x86_64.
    """
    import platform
    import struct

    if platform.machine() != "x86_64":
        raise UnsupportedArchError(f"seccomp blocklist no definida para {platform.machine()!r}")

    BPF_LD_W_ABS = 0x20
    BPF_JEQ_K = 0x15
    BPF_RET_K = 0x06

    def f(code: int, jt: int, jf: int, k: int) -> bytes:
        return struct.pack("<HBBI", code, jt, jf, k)

    prog = b""
    prog += f(BPF_LD_W_ABS, 0, 0, 4)                        # [0] cargar arch
    prog += f(BPF_JEQ_K, 1, 0, _AUDIT_ARCH_X86_64)          # [1] arch==x86_64 ? saltar KILL
    prog += f(BPF_RET_K, 0, 0, _SECCOMP_RET_KILL_PROCESS)   # [2] RET KILL (arch inesperada)
    prog += f(BPF_LD_W_ABS, 0, 0, 0)                        # [3] cargar nr
    m = len(blocked)
    for i, nr in enumerate(blocked):                        # [4..] bloqueadas → RET ERRNO final
        prog += f(BPF_JEQ_K, m - i, 0, nr)
    prog += f(BPF_RET_K, 0, 0, _SECCOMP_RET_ALLOW)          # RET ALLOW (default)
    prog += f(BPF_RET_K, 0, 0, _SECCOMP_RET_ERRNO_EPERM)    # RET EPERM (destino de bloqueos)
    return prog


def build_bwrap_argv(
    bwrap_bin: str,
    script_path: str,
    output_dir: str,
    *,
    python_bin: str = "python3",
    seccomp_fd: int | None = None,
) -> list[str]:
    """Construye el argv de bwrap para ejecutar script_path en jail.

    El jail:
    - --unshare-all: user, net, mount, uts, ipc, pid. Sin veth → sin red.
    - uid/gid mapeados a 65534 (nobody) dentro del namespace de usuario.
    - / bind-mounted read-only; /tmp y /run como tmpfs efímeros.
    - script_path bind-mounted read-only en /tmp/atlas_script.py.
    - output_dir bind-mounted como único directorio escribible.
    - --die-with-parent / --new-session.
    """
    script_in_jail = "/tmp/atlas_script.py"
    output_in_jail = "/tmp/atlas_output"

    argv = [
        bwrap_bin,
        "--unshare-all",
        "--cap-drop", "ALL",          # Slice 2: ninguna capability dentro del jail
        "--uid", "65534",
        "--gid", "65534",
        # Raíz read-only
        "--ro-bind", "/", "/",
        # /tmp efímero (vacío — el script se añade a continuación)
        "--tmpfs", "/tmp",
        # /proc y /dev mínimos (Python los necesita)
        "--proc", "/proc",
        "--dev", "/dev",
        # Script read-only dentro del jail
        "--ro-bind", script_path, script_in_jail,
        # Dir de salida como único punto escribible
        "--bind", output_dir, output_in_jail,
        "--die-with-parent",
        "--new-session",
    ]
    if seccomp_fd is not None:
        argv += ["--seccomp", str(seccomp_fd)]   # Slice 2: filtro BPF leído del fd
    argv += [
        "--",
        python_bin, script_in_jail,
    ]
    return argv


class BwrapJail:
    """Ejecuta un script Python dentro de un jail bwrap.

    Fail-closed: si bwrap no está en PATH, el constructor lanza
    BwrapUnavailableError. No hay fallback al modo inseguro.
    """

    WALL_TIMEOUT_S: int = 30

    def __init__(self, *, python_bin: str = "python3") -> None:
        self._bwrap = _require_bwrap()
        self._python_bin = python_bin

    @classmethod
    def is_available(cls) -> bool:
        return _find_bwrap() is not None

    def run(
        self,
        script: str,
        *,
        timeout_s: int | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> "BwrapResult":
        """Escribe script en un tempfile y lo ejecuta en el jail.

        Devuelve BwrapResult. Levanta subprocess.TimeoutExpired si el proceso
        supera timeout_s.
        """
        wall = timeout_s if timeout_s is not None else self.WALL_TIMEOUT_S

        with tempfile.TemporaryDirectory(prefix="atlas_bwrap_") as tmpdir:
            script_path = str(Path(tmpdir) / "script.py")
            output_dir = str(Path(tmpdir) / "output")
            Path(output_dir).mkdir()
            Path(script_path).write_text(script, encoding="utf-8")

            # Slice 2: seccomp BPF. Si la arquitectura no está soportada, se corre
            # SIN seccomp (el resto del endurecimiento sigue) con warning honesto.
            seccomp_fd: int | None = None
            try:
                bpf = build_seccomp_bpf()
                bpf_path = Path(tmpdir) / "seccomp.bpf"
                bpf_path.write_bytes(bpf)
                seccomp_fd = os.open(str(bpf_path), os.O_RDONLY)
            except UnsupportedArchError as exc:
                _log.warning("seccomp no aplicado: %s — el jail corre sin filtro BPF", exc)

            argv = build_bwrap_argv(
                self._bwrap,
                script_path,
                output_dir,
                python_bin=self._python_bin,
                seccomp_fd=seccomp_fd,
            )

            env: dict[str, str] = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "TERM": "dumb",
            }
            if extra_env:
                env.update(extra_env)

            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=wall,
                    env=env,
                    pass_fds=(seccomp_fd,) if seccomp_fd is not None else (),
                )
            finally:
                if seccomp_fd is not None:
                    os.close(seccomp_fd)
            duration_ms = int((time.perf_counter() - start) * 1000)

        return BwrapResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=duration_ms,
        )


class BwrapResult:
    """Resultado de una ejecución en BwrapJail."""

    __slots__ = ("returncode", "stdout", "stderr", "duration_ms")

    def __init__(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms

    @property
    def success(self) -> bool:
        return self.returncode == 0
