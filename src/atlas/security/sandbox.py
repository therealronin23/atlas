"""
Atlas Core — LayeredIsolationSandbox
Arquitectura de aislamiento de ejecucion por capas segun el chat de Gemini.

Filosofia: "Derecho al Error Fisico"
Antes de ejecutar algo con riesgo (escritura, instalar, modificar), Atlas toma
un snapshot. Si algo sale mal, el usuario puede hacer Undo real a nivel de
filesystem/VM, no solo git revert.

Dos capas:
  NORMAL: código y comandos pasan por un jail bubblewrap sin red y con rootfs
          mínimo. Los comandos ven solo su directorio de trabajo, read-only
          salvo una mutación autorizada explícitamente.
  OMEGA: snapshot del workspace antes de ejecutar para permitir undo físico;
         la ejecución conserva el mismo límite OS fail-closed.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from atlas.core.contracts import OperationalMode
from atlas.security.ast_guard import ASTGuard
from atlas.security.bwrap_jail import BwrapJail, BwrapUnavailableError
from atlas.security.pending_store import pending_hmac_secret
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
    NORMAL tier: bubblewrap + límites CPU/RAM/FSIZE, sin red y con mount
    namespace mínimo. Sin bubblewrap, la ejecución se deniega.
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
        # BwrapJail is lazily created on first use; None if bwrap not available.
        self._bwrap: BwrapJail | None | bool = False  # False = not yet checked

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
            try:
                return self._execute_omega(code, working_dir, snapshot_id, wall)
            except BwrapUnavailableError as exc:
                # ADR-055 fail-closed: sin bwrap, OMEGA se deniega.
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr=f"[jail fail-closed] {exc}",
                    exit_code=-1,
                    duration_ms=0,
                    operational_mode=OperationalMode.OMEGA,
                    snapshot_id=snapshot_id,
                )
        else:
            try:
                return self.execute_in_jail(code, timeout_s=wall)
            except BwrapUnavailableError as exc:
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr=f"[jail fail-closed] {exc}",
                    exit_code=-1,
                    duration_ms=0,
                    operational_mode=OperationalMode.NORMAL,
                )

    def execute_command(
        self,
        command: list[str],
        operational_mode: OperationalMode = OperationalMode.NORMAL,
        working_dir: Path | None = None,
        timeout_s: int | None = None,
        *,
        working_dir_writable: bool = False,
        read_only_paths: tuple[Path, ...] = (),
    ) -> SandboxResult:
        """
        Ejecuta argv (nunca shell) dentro de bubblewrap. El AST Guard no
        aplica: la allowlist y el capability token ya fueron validados antes.
        Fail-closed sin bwrap. El working_dir es read-only por defecto.
        """
        wall = self._effective_timeout(timeout_s)
        cwd = (working_dir or self._workspace).expanduser().resolve(strict=True)
        workspace = self._workspace.expanduser().resolve(strict=True)
        try:
            cwd.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"working_dir fuera del workspace: {cwd}") from exc

        jail = self._get_bwrap()
        if jail is None:
            raise BwrapUnavailableError(
                "bwrap no disponible — comando estructurado bloqueado (ADR-055)."
            )
        self._sync_jail_limits(jail)
        declared_inputs = tuple(path.expanduser().resolve(strict=True) for path in read_only_paths)
        try:
            result = jail.run_command(
                command,
                working_dir=cwd,
                working_dir_writable=working_dir_writable,
                read_only_paths=declared_inputs,
                timeout_s=wall,
            )
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=result.duration_ms,
                operational_mode=operational_mode,
            )
        except (TimeoutError, subprocess.TimeoutExpired):
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Timeout ({wall}s) excedido.",
                exit_code=-1,
                duration_ms=wall * 1000,
                operational_mode=operational_mode,
            )
        except (OSError, ValueError) as e:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                operational_mode=operational_mode,
            )

    # ------------------------------------------------------------------
    # ADR-055: BwrapJail (OS-level containment)
    # ------------------------------------------------------------------

    def _get_bwrap(self) -> BwrapJail | None:
        """Returns a BwrapJail or None if bwrap is unavailable (cached)."""
        if self._bwrap is False:
            try:
                self._bwrap = BwrapJail()
            except BwrapUnavailableError:
                self._bwrap = None
        return self._bwrap  # type: ignore[return-value]

    def execute_in_jail(
        self,
        code: str,
        *,
        timeout_s: int | None = None,
    ) -> SandboxResult:
        """Executes code in a bwrap OS-level jail (ADR-055).

        Fail-closed: raises BwrapUnavailableError if bwrap is not installed.
        Use this instead of execute() for untrusted/model-generated code.
        """
        jail = self._get_bwrap()
        if jail is None:
            raise BwrapUnavailableError(
                "bwrap no disponible — ejecución de código no confiable bloqueada (ADR-055)."
            )
        self._sync_jail_limits(jail)
        # ASTGuard as pre-lint (defense-in-depth, not the security boundary)
        guard_result = self._ast_guard.validate(code)
        if not guard_result.passed:
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"[AST Guard lint] {guard_result.sanitized_reason}",
                exit_code=-1,
                duration_ms=0,
                operational_mode=OperationalMode.NORMAL,
            )
        try:
            result = jail.run(code, timeout_s=timeout_s)
        except (TimeoutError, subprocess.TimeoutExpired):
            wall = timeout_s or BwrapJail.WALL_TIMEOUT_S
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Jail timeout ({wall}s).",
                exit_code=-1,
                duration_ms=wall * 1000,
                operational_mode=OperationalMode.NORMAL,
            )
        return SandboxResult(
            success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=result.duration_ms,
            operational_mode=OperationalMode.NORMAL,
        )

    def _sync_jail_limits(self, jail: BwrapJail) -> None:
        jail.RAM_LIMIT_BYTES = self.RAM_LIMIT_ALFA_BYTES
        jail.CPU_TIME_LIMIT_S = self.CPU_TIME_LIMIT_ALFA_S
        jail.FSIZE_LIMIT_BYTES = self.FSIZE_LIMIT_NORMAL_BYTES

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
        # ADR-055 fail-closed: código OMEGA (alto riesgo) SIEMPRE pasa por jail OS-level.
        # Sin bwrap, denegamos; no degradamos a NORMAL.
        result = self.execute_in_jail(code, timeout_s=timeout_s)
        result.operational_mode = OperationalMode.OMEGA
        result.snapshot_id = snapshot_id
        return result

    def _snapshots_dir(self) -> Path:
        d = self._workspace / self.SNAPSHOT_DIR_NAME
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _archive_path(self, snapshot_id: str) -> Path:
        return self._snapshots_dir() / f"{snapshot_id}.tar.gz"

    def _hmac_path(self, snapshot_id: str) -> Path:
        """Ruta del sidecar HMAC-SHA256 para un snapshot dado."""
        return self._snapshots_dir() / f"{snapshot_id}.tar.hmac"

    def _compute_archive_hmac(self, archive: Path) -> str:
        """Calcula HMAC-SHA256 del archivo .tar.gz usando la clave local de pending_store."""
        key = pending_hmac_secret()
        mac = _hmac.new(key, archive.read_bytes(), hashlib.sha256)
        return mac.hexdigest()

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

        archive = self._archive_path(snapshot_id)
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(str(target), arcname=".", filter=_filter)
        # Persiste el HMAC del archivo recién creado como sidecar 0600.
        mac = self._compute_archive_hmac(archive)
        hmac_path = self._hmac_path(snapshot_id)
        import os as _os
        fd = _os.open(str(hmac_path), _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o600)
        try:
            _os.write(fd, mac.encode("utf-8"))
        finally:
            _os.close(fd)
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str, target: Path | None = None) -> bool:
        """Restaura un snapshot previo sobre ``target`` (default: workspace).

        Fail-closed: rechaza la extracción si:
        - el archivo .tar.gz no existe,
        - el sidecar .hmac no existe, o
        - el HMAC no coincide con el del archivo actual (snapshot envenenado).
        """
        archive = self._archive_path(snapshot_id)
        if not archive.is_file():
            return False
        hmac_path = self._hmac_path(snapshot_id)
        if not hmac_path.is_file():
            # Sin sidecar de integridad → rechazado fail-closed.
            return False
        stored_mac = hmac_path.read_text(encoding="utf-8").strip()
        actual_mac = self._compute_archive_hmac(archive)
        if not _hmac.compare_digest(actual_mac, stored_mac):
            # Archivo manipulado → rechazado fail-closed, no se extrae nada.
            return False
        dest = target or self._workspace
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(str(dest), filter="data")
        return True

    def _safe_env(self) -> dict[str, str]:
        """Entorno minimo seguro para el proceso hijo."""
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self._workspace),
            "PYTHONPATH": "",
            "TERM": "dumb",
        }
