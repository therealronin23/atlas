"""
BwrapJail — OS-level jail para código no confiable (ADR-055 Slice 1).

El límite de seguridad real es el kernel: uid separado + namespaces + montaje ro.
ASTGuard es defensa en profundidad (lint), no contención — este módulo es la contención.

Propiedades enforced:
  1. uid/gid 65534 (nobody) via user namespace
  2. Network namespace sin veth — red bloqueada en el kernel
  3. Rootfs mínimo (/usr ro + symlinks); /tmp como tmpfs efímero; sin $HOME
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
from typing import BinaryIO, Sequence

_log = logging.getLogger(__name__)

_DEFAULT_RAM_BYTES = 512 * 1024 * 1024
_DEFAULT_CPU_SECONDS = 30
_DEFAULT_FSIZE_BYTES = 64 * 1024 * 1024
_DEFAULT_NOFILE = 256
_DEFAULT_NPROC = 256

# Los límites se aplican DESPUÉS de que bwrap haya creado namespaces/mounts.
# Aplicarlos como preexec_fn al propio bwrap impide crear el user namespace en
# kernels que contabilizan esos clones contra RLIMIT_NPROC. Los hard limits y
# no-new-privs se heredan de este lanzador al comando final y no son reversibles.
_LIMIT_WRAPPER = """
import ctypes, os, resource, sys
ram, cpu, fsize, nofile, nproc = map(int, sys.argv[1:6])
limits = [
    (resource.RLIMIT_CORE, 0),
    (resource.RLIMIT_AS, ram),
    (resource.RLIMIT_CPU, cpu),
    (resource.RLIMIT_FSIZE, fsize),
    (resource.RLIMIT_NOFILE, nofile),
]
if hasattr(resource, 'RLIMIT_NPROC'):
    limits.append((resource.RLIMIT_NPROC, nproc))
for kind, value in limits:
    try:
        resource.setrlimit(kind, (value, value))
    except (ValueError, OSError):
        pass
try:
    libc = ctypes.CDLL('libc.so.6', use_errno=True)
    libc.prctl(38, 1, 0, 0, 0)
except Exception:
    pass
try:
    os.setsid()
except OSError:
    pass
command = sys.argv[6:]
if not command:
    raise SystemExit(126)
os.execvp(command[0], command)
""".strip()


def _limited_command(
    command: Sequence[str],
    *,
    ram_bytes: int,
    cpu_seconds: int,
    fsize_bytes: int,
    nofile: int,
    nproc: int,
) -> list[str]:
    return [
        "python3", "-c", _LIMIT_WRAPPER,
        str(ram_bytes), str(cpu_seconds), str(fsize_bytes),
        str(nofile), str(nproc),
        *command,
    ]


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
    323,  # userfaultfd      — LPE vía kernel UAF chains
    425,  # io_uring_setup   — LPE via io_uring subsystem
    426,  # io_uring_enter
    427,  # io_uring_register
    435,  # clone3           — bypass de filtros de clone flags
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
    ram_bytes: int = _DEFAULT_RAM_BYTES,
    cpu_seconds: int = _DEFAULT_CPU_SECONDS,
    fsize_bytes: int = _DEFAULT_FSIZE_BYTES,
    nofile: int = _DEFAULT_NOFILE,
    nproc: int = _DEFAULT_NPROC,
) -> list[str]:
    """Construye el argv de bwrap para ejecutar script_path en jail.

    El jail:
    - --unshare-all: user, net, mount, uts, ipc, pid. Sin veth → sin red.
    - uid/gid mapeados a 65534 (nobody) dentro del namespace de usuario.
    - Rootfs MÍNIMO: solo /usr (+ symlinks para /bin /lib /lib64 /sbin),
      /etc/ssl (certs SSL para Python), /tmp efímero, /proc y /dev mínimos.
      NO se monta $HOME ni / completo → los secretos del host (~/.ssh, .env,
      .aws) son inaccesibles dentro del jail.
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
        # Rootfs mínimo: solo /usr (contiene bin, lib, lib64, sbin en sistemas mergedusr)
        "--ro-bind", "/usr", "/usr",
        # Symlinks para distros usr-merged (bin → usr/bin, lib → usr/lib, etc.)
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/sbin", "/sbin",
        # SSL certs para Python (urllib/ssl)
        "--ro-bind", "/etc/ssl", "/etc/ssl",
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
    argv += ["--", *_limited_command(
        [python_bin, script_in_jail],
        ram_bytes=ram_bytes,
        cpu_seconds=cpu_seconds,
        fsize_bytes=fsize_bytes,
        nofile=nofile,
        nproc=nproc,
    )]
    return argv


def _mount_parent_argv(destinations: Sequence[Path]) -> list[str]:
    """Crea solo los padres sintéticos necesarios para bind mounts puntuales."""
    base_dirs = {
        Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64"),
        Path("/sbin"), Path("/etc"), Path("/etc/ssl"), Path("/tmp"),
        Path("/proc"), Path("/dev"),
    }
    parents: set[Path] = set()
    for destination in destinations:
        for parent in destination.parents:
            if parent == Path("/") or parent in base_dirs:
                continue
            if any(parent == base or base in parent.parents for base in base_dirs):
                # Descendientes de /tmp sí deben crearse dentro del tmpfs; los
                # demás roots base ya existen y no deben sombrearse.
                if Path("/tmp") not in parent.parents:
                    continue
            parents.add(parent)
    argv: list[str] = []
    for parent in sorted(parents, key=lambda item: (len(item.parts), str(item))):
        argv.extend(("--dir", str(parent)))
    return argv


def build_command_bwrap_argv(
    bwrap_bin: str,
    command: Sequence[str],
    working_dir: str,
    *,
    working_dir_writable: bool = False,
    read_only_paths: Sequence[str] = (),
    seccomp_fd: int | None = None,
    ram_bytes: int = _DEFAULT_RAM_BYTES,
    cpu_seconds: int = _DEFAULT_CPU_SECONDS,
    fsize_bytes: int = _DEFAULT_FSIZE_BYTES,
    nofile: int = _DEFAULT_NOFILE,
    nproc: int = _DEFAULT_NPROC,
) -> list[str]:
    """Construye un jail para un comando estructurado, sin montar el host.

    El directorio de trabajo es el único árbol visible aportado por el
    llamador y es read-only por defecto. Entradas adicionales deben declararse
    explícitamente y se montan read-only en su misma ruta absoluta.
    """
    if not command or not command[0]:
        raise ValueError("comando vacio")

    cwd = Path(working_dir).expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError(f"working_dir no es directorio: {cwd}")

    mounts: list[tuple[Path, Path]] = []
    for raw in read_only_paths:
        lexical = Path(raw).expanduser()
        if not lexical.is_absolute():
            raise ValueError(f"read_only_path debe ser absoluto: {raw}")
        source = lexical.resolve(strict=True)
        destination = Path(os.path.abspath(str(lexical)))
        mounts.append((source, destination))

    destinations = [cwd, *(destination for _source, destination in mounts)]
    argv = [
        bwrap_bin,
        "--unshare-all",
        "--cap-drop", "ALL",
        "--uid", "65534",
        "--gid", "65534",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/sbin", "/sbin",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
        *_mount_parent_argv(destinations),
        "--bind" if working_dir_writable else "--ro-bind", str(cwd), str(cwd),
    ]
    for source, destination in mounts:
        argv.extend(("--ro-bind", str(source), str(destination)))
    argv.extend((
        "--chdir", str(cwd),
        "--die-with-parent",
        "--new-session",
    ))
    if seccomp_fd is not None:
        argv.extend(("--seccomp", str(seccomp_fd)))
    argv.extend(("--", *_limited_command(
        command,
        ram_bytes=ram_bytes,
        cpu_seconds=cpu_seconds,
        fsize_bytes=fsize_bytes,
        nofile=nofile,
        nproc=nproc,
    )))
    return argv


class BwrapJail:
    """Ejecuta un script Python dentro de un jail bwrap.

    Fail-closed: si bwrap no está en PATH, el constructor lanza
    BwrapUnavailableError. No hay fallback al modo inseguro.
    """

    WALL_TIMEOUT_S: int = 30
    RAM_LIMIT_BYTES: int = _DEFAULT_RAM_BYTES
    CPU_TIME_LIMIT_S: int = _DEFAULT_CPU_SECONDS
    FSIZE_LIMIT_BYTES: int = _DEFAULT_FSIZE_BYTES
    NOFILE_LIMIT: int = _DEFAULT_NOFILE
    NPROC_LIMIT: int = _DEFAULT_NPROC
    MAX_CAPTURE_BYTES: int = 1024 * 1024

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
                ram_bytes=self.RAM_LIMIT_BYTES,
                cpu_seconds=self.CPU_TIME_LIMIT_S,
                fsize_bytes=self.FSIZE_LIMIT_BYTES,
                nofile=self.NOFILE_LIMIT,
                nproc=self.NPROC_LIMIT,
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
                proc, stdout, stderr = self._run_process(
                    argv,
                    wall=wall,
                    env=env,
                    seccomp_fd=seccomp_fd,
                )
            finally:
                if seccomp_fd is not None:
                    os.close(seccomp_fd)
            duration_ms = int((time.perf_counter() - start) * 1000)

        return BwrapResult(
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )

    def run_command(
        self,
        command: Sequence[str],
        *,
        working_dir: Path,
        working_dir_writable: bool = False,
        read_only_paths: Sequence[Path] = (),
        timeout_s: int | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> "BwrapResult":
        """Ejecuta argv sin shell dentro de un mount/net namespace mínimo."""
        wall = timeout_s if timeout_s is not None else self.WALL_TIMEOUT_S
        with tempfile.TemporaryDirectory(prefix="atlas_bwrap_command_") as tmpdir:
            seccomp_fd: int | None = None
            try:
                bpf_path = Path(tmpdir) / "seccomp.bpf"
                bpf_path.write_bytes(build_seccomp_bpf())
                seccomp_fd = os.open(str(bpf_path), os.O_RDONLY)
            except UnsupportedArchError as exc:
                _log.warning("seccomp no aplicado: %s — el jail corre sin filtro BPF", exc)

            argv = build_command_bwrap_argv(
                self._bwrap,
                command,
                str(working_dir),
                working_dir_writable=working_dir_writable,
                read_only_paths=tuple(str(path) for path in read_only_paths),
                seccomp_fd=seccomp_fd,
                ram_bytes=self.RAM_LIMIT_BYTES,
                cpu_seconds=self.CPU_TIME_LIMIT_S,
                fsize_bytes=self.FSIZE_LIMIT_BYTES,
                nofile=self.NOFILE_LIMIT,
                nproc=self.NPROC_LIMIT,
            )
            env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "TERM": "dumb",
                "GIT_OPTIONAL_LOCKS": "0",
            }
            if extra_env:
                env.update(extra_env)

            start = time.perf_counter()
            try:
                proc, stdout, stderr = self._run_process(
                    argv,
                    wall=wall,
                    env=env,
                    seccomp_fd=seccomp_fd,
                )
            finally:
                if seccomp_fd is not None:
                    os.close(seccomp_fd)
            duration_ms = int((time.perf_counter() - start) * 1000)

        return BwrapResult(
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )

    def _run_process(
        self,
        argv: Sequence[str],
        *,
        wall: int,
        env: dict[str, str],
        seccomp_fd: int | None,
    ) -> tuple[subprocess.CompletedProcess[bytes], str, str]:
        """Ejecuta con captura acotada respaldada por ficheros."""
        with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
            mode="w+b"
        ) as stderr_file:
            proc = subprocess.run(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=wall,
                env=env,
                pass_fds=(seccomp_fd,) if seccomp_fd is not None else (),
                start_new_session=True,
            )
            stdout = self._read_capture(stdout_file, getattr(proc, "stdout", None))
            stderr = self._read_capture(stderr_file, getattr(proc, "stderr", None))
        return proc, stdout, stderr

    def _read_capture(self, stream: BinaryIO, fallback: object) -> str:
        stream.flush()
        size = os.fstat(stream.fileno()).st_size
        stream.seek(0)
        raw = stream.read(self.MAX_CAPTURE_BYTES)
        text = raw.decode("utf-8", errors="replace")
        if size > self.MAX_CAPTURE_BYTES:
            text += "\n[atlas: output truncated]\n"
        if not text and isinstance(fallback, str):
            return fallback[: self.MAX_CAPTURE_BYTES]
        return text


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
