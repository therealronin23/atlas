"""
Atlas Core — LayeredIsolationSandbox
Arquitectura de aislamiento de ejecucion por capas segun el chat de Gemini.

Filosofia: "Derecho al Error Fisico"
Antes de ejecutar algo con riesgo (escritura, instalar, modificar), Atlas toma
un snapshot. Si algo sale mal, el usuario puede hacer Undo real a nivel de
filesystem/VM, no solo git revert.

Dos capas:
  NORMAL tier (subprocess aislado): Subprocess aislado con CPU/RAM limitados.
                      Sin acceso de red. Solo workspace. 512MB RAM max.
  OMEGA (alto riesgo): snapshot del workspace antes de ejecutar para permitir
                       undo fisico (restore_snapshot). La ejecucion corre en el
                       mismo tier NORMAL endurecido; el aislamiento por VM real
                       (Proxmox) queda fuera de alcance del host local.
"""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from atlas.core.contracts import OperationalMode
from atlas.security.ast_guard import ASTGuard
from atlas.security.process_hardening import apply_in_child


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    operational_mode: OperationalMode
    snapshot_id: str | None = None   # Si se creo snapshot antes de ejecutar


class LayeredIsolationSandbox:
    """
    Sandbox de ejecucion de codigo por capas.
    NORMAL tier: subprocess aislado con limites de recursos.
    OMEGA: snapshot local del workspace (tarfile) antes de ejecutar + restore.
    """

    RAM_LIMIT_ALFA_BYTES  = 512 * 1024 * 1024   # 512 MB
    CPU_TIME_LIMIT_ALFA_S = 30                   # 30 segundos CPU
    WALL_TIMEOUT_NORMAL_S   = 60                   # 60 segundos real (default)
    FSIZE_LIMIT_NORMAL_BYTES = 64 * 1024 * 1024  # ADR-034: 64 MB por archivo
    SNAPSHOT_DIR_NAME = ".atlas_snapshots"
    _SNAPSHOT_EXCLUDED = frozenset({SNAPSHOT_DIR_NAME, "tmp", "__pycache__"})

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._ast_guard = ASTGuard()

    def execute(
        self,
        code: str,
        operational_mode: OperationalMode = OperationalMode.NORMAL,
        working_dir: Path | None = None,
        take_snapshot: bool = False,
        timeout_s: int | None = None,
    ) -> SandboxResult:
        """
        Ejecuta codigo Python en el sandbox apropiado segun el operational_mode.
        SIEMPRE pasa por AST Guard antes de ejecutar.
        """
        wall = self._effective_timeout(timeout_s)
        # 1. AST Guard obligatorio (microsegundos, sin ejecutar nada)
        guard_result = self._ast_guard.validate(code)
        if not guard_result.passed:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"[AST Guard] Codigo rechazado: {guard_result.sanitized_reason}",
                exit_code=-1,
                duration_ms=0,
                operational_mode=operational_mode,
            )

        # 2. OMEGA: snapshot real del workspace antes de ejecutar (undo fisico).
        snapshot_id = None
        if take_snapshot and operational_mode == OperationalMode.OMEGA:
            snapshot_id = self._take_snapshot(working_dir or self._workspace)

        # 3. Ejecutar segun modo
        if operational_mode == OperationalMode.OMEGA:
            return self._execute_omega(code, working_dir, snapshot_id, wall)
        else:
            return self._execute_normal(code, working_dir, wall)

    def execute_command(
        self,
        command: list[str],
        operational_mode: OperationalMode = OperationalMode.NORMAL,
        working_dir: Path | None = None,
        timeout_s: int | None = None,
    ) -> SandboxResult:
        """
        Ejecuta un comando shell (no Python) con limites de recursos.
        El AST Guard no aplica aqui — la allowlist de Permission Profile
        ya lo valido antes de llegar a este punto.
        """
        wall = self._effective_timeout(timeout_s)
        cwd = working_dir or self._workspace
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=wall,
                env=self._safe_env(),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                operational_mode=operational_mode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Timeout ({wall}s) excedido.",
                exit_code=-1,
                duration_ms=wall * 1000,
                operational_mode=operational_mode,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                operational_mode=operational_mode,
            )

    # ------------------------------------------------------------------
    # NORMAL tier: subprocess con resource limits
    # ------------------------------------------------------------------

    def _effective_timeout(self, timeout_s: int | None) -> int:
        return timeout_s if timeout_s is not None else self.WALL_TIMEOUT_NORMAL_S

    def _execute_normal(
        self, code: str, working_dir: Path | None, timeout_s: int | None = None
    ) -> SandboxResult:
        timeout_s = self._effective_timeout(timeout_s)
        cwd = working_dir or self._workspace
        start = time.perf_counter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(self._workspace / "tmp")
        ) as f:
            f.write(code)
            script_path = f.name

        def _set_limits() -> None:
            """ADR-034: endurecimiento del hijo (rlimits + no-new-privs).
            Tolerante a fallo; ver process_hardening.apply_in_child."""
            apply_in_child(
                ram_bytes=self.RAM_LIMIT_ALFA_BYTES,
                cpu_seconds=self.CPU_TIME_LIMIT_ALFA_S,
                fsize_bytes=self.FSIZE_LIMIT_NORMAL_BYTES,
            )

        try:
            result = subprocess.run(
                ["python3", script_path],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_set_limits,
                start_new_session=True,  # ADR-034 dec.3: sesión aislada
                env=self._safe_env(),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                operational_mode=OperationalMode.NORMAL,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Sandbox NORMAL timeout ({timeout_s}s).",
                exit_code=-1,
                duration_ms=timeout_s * 1000,
                operational_mode=OperationalMode.NORMAL,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                operational_mode=OperationalMode.NORMAL,
            )
        finally:
            try:
                Path(script_path).unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # OMEGA: ejecucion con snapshot local del workspace (undo fisico)
    # ------------------------------------------------------------------

    def _execute_omega(
        self,
        code: str,
        working_dir: Path | None,
        snapshot_id: str | None,
        timeout_s: int,
    ) -> SandboxResult:
        result = self._execute_normal(code, working_dir, timeout_s)
        result.operational_mode = OperationalMode.OMEGA
        result.snapshot_id = snapshot_id
        return result

    def _snapshots_dir(self) -> Path:
        d = self._workspace / self.SNAPSHOT_DIR_NAME
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _archive_path(self, snapshot_id: str) -> Path:
        return self._snapshots_dir() / f"{snapshot_id}.tar.gz"

    def _take_snapshot(self, target: Path) -> str:
        """Empaqueta ``target`` en un tar.gz local; devuelve el snapshot_id.

        Excluye el propio directorio de snapshots, ``tmp`` y ``__pycache__``
        para evitar recursion y ruido regenerable.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        snapshot_id = f"atlas-snap-{ts}"
        excluded = self._SNAPSHOT_EXCLUDED

        def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
            parts = Path(info.name).parts
            return None if any(p in excluded for p in parts) else info

        with tarfile.open(self._archive_path(snapshot_id), "w:gz") as tar:
            tar.add(str(target), arcname=".", filter=_filter)
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str, target: Path | None = None) -> bool:
        """Restaura un snapshot previo sobre ``target`` (default: workspace).

        Devuelve False si el archivo no existe. El contenido es de confianza
        (lo generamos nosotros), pero usamos el filtro ``data`` por defensa.
        """
        archive = self._archive_path(snapshot_id)
        if not archive.is_file():
            return False
        dest = target or self._workspace
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(str(dest), filter="data")
        return True

    def _safe_env(self) -> dict:
        """Entorno minimo seguro para el proceso hijo."""
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self._workspace),
            "PYTHONPATH": "",
            "TERM": "dumb",
        }
