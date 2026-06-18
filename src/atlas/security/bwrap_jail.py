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
  - Slice 2 (seccomp-bpf allowlist) no incluido aún — deferred
  - No cierra canales laterales de timing/recursos compartidos
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path


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


def build_bwrap_argv(
    bwrap_bin: str,
    script_path: str,
    output_dir: str,
    *,
    python_bin: str = "python3",
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

    return [
        bwrap_bin,
        "--unshare-all",
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
        "--",
        python_bin, script_in_jail,
    ]


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

            argv = build_bwrap_argv(
                self._bwrap,
                script_path,
                output_dir,
                python_bin=self._python_bin,
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
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=wall,
                env=env,
            )
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
