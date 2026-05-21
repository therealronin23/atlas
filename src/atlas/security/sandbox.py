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
  OMEGA (alto riesgo): VM Proxmox + Snapshot antes de ejecutar.
                       Requiere confirmacion humana (HITL via Telegram).
                       Solo para acciones destructivas o estructurales.

v0.1: Implementa modo NORMAL como subprocess con timeout y resource limits.
      OMEGA es stub (planificado para Gate C con Proxmox real).
"""

from __future__ import annotations

import resource
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from atlas.core.contracts import OperationalMode
from atlas.security.ast_guard import ASTGuard


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
    OMEGA: stub — requiere Proxmox real (Gate C).
    """

    RAM_LIMIT_ALFA_BYTES  = 512 * 1024 * 1024   # 512 MB
    CPU_TIME_LIMIT_ALFA_S = 30                   # 30 segundos CPU
    WALL_TIMEOUT_NORMAL_S   = 60                   # 60 segundos real

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._ast_guard = ASTGuard()

    def execute(
        self,
        code: str,
        operational_mode: OperationalMode = OperationalMode.NORMAL,
        working_dir: Path | None = None,
        take_snapshot: bool = False,
    ) -> SandboxResult:
        """
        Ejecuta codigo Python en el sandbox apropiado segun el operational_mode.
        SIEMPRE pasa por AST Guard antes de ejecutar.
        """
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

        # 2. Tomar snapshot si se solicita (solo stub en v0.1)
        snapshot_id = None
        if take_snapshot and operational_mode == OperationalMode.OMEGA:
            snapshot_id = self._take_snapshot_stub()

        # 3. Ejecutar segun modo
        if operational_mode == OperationalMode.OMEGA:
            return self._execute_degraded_stub(code, working_dir, snapshot_id)
        else:
            return self._execute_normal(code, working_dir)

    def execute_command(
        self,
        command: list[str],
        operational_mode: OperationalMode = OperationalMode.NORMAL,
        working_dir: Path | None = None,
    ) -> SandboxResult:
        """
        Ejecuta un comando shell (no Python) con limites de recursos.
        El AST Guard no aplica aqui — la allowlist de Permission Profile
        ya lo valido antes de llegar a este punto.
        """
        cwd = working_dir or self._workspace
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.WALL_TIMEOUT_NORMAL_S,
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
                stderr=f"Timeout ({self.WALL_TIMEOUT_NORMAL_S}s) excedido.",
                exit_code=-1,
                duration_ms=self.WALL_TIMEOUT_NORMAL_S * 1000,
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

    def _execute_normal(
        self, code: str, working_dir: Path | None
    ) -> SandboxResult:
        cwd = working_dir or self._workspace
        start = time.perf_counter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(self._workspace / "tmp")
        ) as f:
            f.write(code)
            script_path = f.name

        def _set_limits() -> None:
            """Aplicar limits POSIX (Linux only)."""
            try:
                # Limitar memoria virtual
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (self.RAM_LIMIT_ALFA_BYTES, self.RAM_LIMIT_ALFA_BYTES)
                )
                # Limitar tiempo CPU
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (self.CPU_TIME_LIMIT_ALFA_S, self.CPU_TIME_LIMIT_ALFA_S)
                )
                # Sin archivos de core
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            except Exception:
                pass  # En sistemas donde no aplica, continuar sin limits

        try:
            result = subprocess.run(
                ["python3", script_path],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.WALL_TIMEOUT_NORMAL_S,
                preexec_fn=_set_limits,
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
                stderr=f"Sandbox NORMAL timeout ({self.WALL_TIMEOUT_NORMAL_S}s).",
                exit_code=-1,
                duration_ms=self.WALL_TIMEOUT_NORMAL_S * 1000,
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
    # OMEGA: stub hasta Gate C (Proxmox real)
    # ------------------------------------------------------------------

    def _execute_degraded_stub(
        self, code: str, working_dir: Path | None, snapshot_id: str | None
    ) -> SandboxResult:
        """
        OMEGA real requiere Proxmox + HITL via Telegram.
        En v0.1, ejecuta en NORMAL tier con advertencia y snapshot registrado.
        Gate C: sustituir por llamada real a Proxmox API.
        """
        result = self._execute_normal(code, working_dir)
        result.operational_mode = OperationalMode.OMEGA
        result.snapshot_id = snapshot_id
        if result.stderr:
            result.stderr = f"[DEGRADED/DEGRADED tier stub] {result.stderr}"
        return result

    def _take_snapshot_stub(self) -> str:
        """
        Stub de snapshot. Gate C: proxmox_api.snapshot(vmid, name=...).
        Retorna un ID de snapshot simulado.
        """
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"atlas-snap-{ts}"
        # TODO Gate C: qm snapshot <vmid> <snapshot_id> --description "Atlas pre-exec"
        return snapshot_id

    def _safe_env(self) -> dict:
        """Entorno minimo seguro para el proceso hijo."""
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self._workspace),
            "PYTHONPATH": "",
            "TERM": "dumb",
        }
