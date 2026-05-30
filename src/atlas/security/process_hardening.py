"""
Atlas Core — Endurecimiento de subprocess (ADR-034, Post-F hardening).

Funciones stdlib-only para reforzar el subprocess que ejecuta código no
confiable. Pensado para usarse como `preexec_fn` de `subprocess.run/Popen`
(combinado con `start_new_session=True` para aislar la sesión).

Capas:
  - rlimits: CPU, memoria virtual, tamaño de archivo, nº de procesos, nº de
    descriptores, sin core dumps.
  - PR_SET_NO_NEW_PRIVS: corta la escalada de privilegios vía binarios setuid.

Diseño defensivo: NADA aquí lanza. Un preexec_fn que lance mata al hijo antes
del exec, así que cada paso degrada a no-op silencioso si la plataforma no lo
soporta (no-Linux, contenedores restringidos, etc.).

Punto de extensión: `apply_in_child` es el único hook que el sandbox invoca;
aquí se añadiría en el futuro un filtro seccomp-bpf (requeriría dep nueva, fuera
de alcance — ADR-034 dec.6).
"""

from __future__ import annotations

import ctypes
import resource

# prctl(2): PR_SET_NO_NEW_PRIVS == 38. Una vez puesto a 1, ni el proceso ni sus
# hijos pueden ganar privilegios vía execve de binarios setuid/setgid.
PR_SET_NO_NEW_PRIVS = 38

# Defaults conservadores para ejecución no confiable en el NORMAL tier.
DEFAULT_RAM_BYTES = 512 * 1024 * 1024   # 512 MB de memoria virtual
DEFAULT_CPU_SECONDS = 30                # 30 s de CPU
DEFAULT_FSIZE_BYTES = 64 * 1024 * 1024  # 64 MB por archivo escrito
DEFAULT_NOFILE = 256                    # descriptores abiertos
DEFAULT_NPROC = 256                     # procesos/hilos (anti fork-bomb)


def default_rlimits(
    *,
    ram_bytes: int = DEFAULT_RAM_BYTES,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    fsize_bytes: int = DEFAULT_FSIZE_BYTES,
    nofile: int = DEFAULT_NOFILE,
    nproc: int = DEFAULT_NPROC,
) -> list[tuple[int, tuple[int, int]]]:
    """Devuelve la lista de (RLIMIT_*, (soft, hard)) a aplicar en el hijo.

    Función pura: no toca el proceso, solo construye la tabla. Así es testeable
    sin forkear. RLIMIT_NPROC y RLIMIT_FSIZE pueden no existir en plataformas
    no-POSIX; el aplicador los salta si faltan.
    """
    limits: list[tuple[int, tuple[int, int]]] = [
        (resource.RLIMIT_AS, (ram_bytes, ram_bytes)),
        (resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds)),
        (resource.RLIMIT_CORE, (0, 0)),
        (resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes)),
        (resource.RLIMIT_NOFILE, (nofile, nofile)),
    ]
    # RLIMIT_NPROC no está en todas las plataformas (p.ej. algunos macOS/BSD).
    rlimit_nproc = getattr(resource, "RLIMIT_NPROC", None)
    if rlimit_nproc is not None:
        limits.append((rlimit_nproc, (nproc, nproc)))
    return limits


def set_no_new_privs() -> bool:
    """Aplica PR_SET_NO_NEW_PRIVS al proceso actual. Devuelve True si tuvo éxito.

    Es irreversible (por diseño del kernel) y se hereda por los hijos. Se llama
    dentro del preexec_fn del hijo, NO en el proceso padre. Cualquier fallo
    (no-Linux, sin libc, prctl ausente) devuelve False sin lanzar.
    """
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        return False
    try:
        # prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        ret = libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        return ret == 0
    except Exception:
        return False


def apply_in_child(
    *,
    ram_bytes: int = DEFAULT_RAM_BYTES,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    fsize_bytes: int = DEFAULT_FSIZE_BYTES,
    nofile: int = DEFAULT_NOFILE,
    nproc: int = DEFAULT_NPROC,
) -> None:
    """Endurece el proceso hijo. Para usar como cuerpo de un `preexec_fn`.

    Aplica todos los rlimits y no-new-privs. Cada paso es tolerante a fallo: si
    un rlimit no se puede fijar (o no existe), se salta y se continúa. NUNCA
    lanza, porque una excepción aquí mataría al hijo antes del execve.
    """
    for rlimit, bounds in default_rlimits(
        ram_bytes=ram_bytes,
        cpu_seconds=cpu_seconds,
        fsize_bytes=fsize_bytes,
        nofile=nofile,
        nproc=nproc,
    ):
        try:
            resource.setrlimit(rlimit, bounds)
        except (ValueError, OSError):
            continue
    set_no_new_privs()
