"""
Atlas Core — Editor Integration Tool (Gate F/F2)
Integracion con Cursor / VS Code para manipulacion de proyectos.

Herramientas:
  - editor.open_project: abre un proyecto en el editor detectado.
  - editor.read_file: lee contenido de un archivo del proyecto.
  - editor.write_file: escribe contenido en un archivo del proyecto.
  - editor.apply_diff: aplica un diff unificado a un archivo.
  - editor.run_task: ejecuta un comando en el directorio del proyecto.

Todas las operaciones pasan por PermissionProfile (paths) y MerkleLogger.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.governance.permission_profile import PermissionProfile
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.capabilities import CapabilityDenied
from atlas.security.executor import AtlasExecutor, ExecutorError
from atlas.security.sandbox import LayeredIsolationSandbox


# ---------------------------------------------------------------------------
# Resultados tipados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditorInfo:
    name: str
    binary: str
    version: str | None
    available: bool


@dataclass(frozen=True)
class OpenResult:
    success: bool
    editor: str
    project_path: str
    error: str | None = None


@dataclass(frozen=True)
class FileReadResult:
    success: bool
    path: str
    content: str
    size_bytes: int
    error: str | None = None


@dataclass(frozen=True)
class FileWriteResult:
    success: bool
    path: str
    bytes_written: int
    error: str | None = None


@dataclass(frozen=True)
class DiffResult:
    success: bool
    file: str
    applied: bool
    stdout: str
    stderr: str
    error: str | None = None


@dataclass(frozen=True)
class TaskResult:
    success: bool
    command: str
    working_dir: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# EditorTool
# ---------------------------------------------------------------------------


class EditorTool:
    """
    Integracion con editores de codigo (Cursor, VS Code, fallback a editor
    de terminal). Detecta el editor disponible al arrancar.

    Uso tipico:

        et = EditorTool(workspace=Path("~/proyectos"))
        info = et.detect_editor()
        et.open_project(Path("~/proyectos/app"))
        content = et.read_file(Path("~/proyectos/app/src/main.py"))
        result = et.apply_diff(Path("file.py"), diff_text)
        task = et.run_task(Path("~/proyectos/app"), "npm test")
    """

    # Orden de preferencia para detectar editor
    _CANDIDATES = [
        ("cursor", "cursor"),
        ("vscode", "code"),
        ("vscode-insiders", "code-insiders"),
        ("vim", "vim"),
        ("nano", "nano"),
    ]

    def __init__(self, workspace: Path, executor: AtlasExecutor | None = None) -> None:
        self._workspace = workspace.expanduser().resolve()
        self._executor = executor or self._build_default_executor(self._workspace)
        self._editor: EditorInfo | None = None

    # ------------------------------------------------------------------
    # Deteccion de editor
    # ------------------------------------------------------------------

    def detect_editor(self, force: str | None = None) -> EditorInfo:
        """
        Detecta el editor disponible. Si force no es None, busca ese binario.
        Cachea el resultado para la sesion.
        """
        candidates = self._CANDIDATES
        if force is not None:
            candidates = [(force, force)]

        for name, binary in candidates:
            path = shutil.which(binary)
            if path is None:
                continue
            version = self._get_version(binary)
            self._editor = EditorInfo(
                name=name, binary=str(path), version=version, available=True,
            )
            return self._editor

        self._editor = EditorInfo(
            name="none", binary="", version=None, available=False,
        )
        return self._editor

    @property
    def editor(self) -> EditorInfo:
        if self._editor is None:
            self.detect_editor()
        assert self._editor is not None
        return self._editor

    # ------------------------------------------------------------------
    # open_project
    # ------------------------------------------------------------------

    def open_project(self, project_path: Path) -> OpenResult:
        """Abre un proyecto en el editor detectado."""
        info = self.editor
        if not info.available:
            return OpenResult(
                success=False, editor="none",
                project_path=str(project_path),
                error="No se detecto editor disponible. Instala Cursor o VS Code.",
            )

        resolved = project_path.expanduser().resolve()
        if not resolved.exists():
            return OpenResult(
                success=False, editor=info.name,
                project_path=str(resolved),
                error=f"El directorio no existe: {resolved}",
            )

        try:
            subprocess.Popen(
                [info.binary, str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return OpenResult(
                success=True, editor=info.name, project_path=str(resolved),
            )
        except Exception as e:
            return OpenResult(
                success=False, editor=info.name,
                project_path=str(resolved),
                error=str(e),
            )

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------

    def read_file(self, path: Path, *, max_bytes: int = 1_000_000) -> FileReadResult:
        """Lee el contenido de un archivo en el proyecto."""
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=f"Archivo no encontrado: {resolved}",
            )
        if not resolved.is_file():
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=f"No es un archivo regular: {resolved}",
            )

        try:
            cap = self._executor.issuer.issue_read(resolved, max_bytes=max_bytes)
            data = self._executor.execute_read(cap)
            if resolved.stat().st_size > max_bytes:
                return FileReadResult(
                    success=False, path=str(resolved), content="", size_bytes=len(data),
                    error=(
                        f"Archivo demasiado grande "
                        f"({resolved.stat().st_size}B > {max_bytes}B max)"
                    ),
                )
            content = data.decode("utf-8")
            return FileReadResult(
                success=True, path=str(resolved), content=content,
                size_bytes=len(content.encode("utf-8")),
            )
        except CapabilityDenied as e:
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=e.reason,
            )
        except ExecutorError as e:
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=str(e),
            )
        except UnicodeDecodeError as e:
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=f"No es texto UTF-8: {e}",
            )
        except Exception as e:
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # write_file
    # ------------------------------------------------------------------

    def write_file(
        self,
        path: Path,
        content: str,
        *,
        clearance: str | None = None,
    ) -> FileWriteResult:
        """Escribe contenido en un archivo (crea directorios si es necesario)."""
        resolved = path.expanduser().resolve()
        try:
            encoded = content.encode("utf-8")
            cap = self._executor.issuer.issue_write(
                resolved,
                max_bytes=max(len(encoded), 1),
                clearance=clearance,
            )
            bytes_written = self._executor.execute_write(cap, encoded)
            return FileWriteResult(
                success=True, path=str(resolved), bytes_written=bytes_written,
            )
        except CapabilityDenied as e:
            return FileWriteResult(
                success=False, path=str(resolved), bytes_written=0, error=e.reason,
            )
        except ExecutorError as e:
            return FileWriteResult(
                success=False, path=str(resolved), bytes_written=0, error=str(e),
            )
        except Exception as e:
            return FileWriteResult(
                success=False, path=str(resolved), bytes_written=0, error=str(e),
            )

    # ------------------------------------------------------------------
    # apply_diff
    # ------------------------------------------------------------------

    def apply_diff(
        self,
        file_path: Path,
        diff_text: str,
        *,
        clearance: str | None = None,
    ) -> DiffResult:
        """
        Aplica un diff unificado a un archivo usando `patch`.
        Desde SEC-01 `git apply` está bloqueado como verbo mutante (no debe ser
        invocable por shell crudo); la ruta sancionada del editor aplica el diff
        con `patch` (gateado por HITL + AtlasExecutor). Si el archivo está bajo un
        repo git se ejecuta `patch` desde la raíz del repo (los diffs `a/`/`b/`
        resuelven con `-p1`); si no, desde el directorio del archivo.
        """
        resolved = file_path.expanduser().resolve()
        git_dir = self._find_git_dir(resolved)
        diff_path = self._write_tmp_diff(diff_text)

        try:
            patch_cwd = git_dir if git_dir is not None else resolved.parent
            return self._try_patch_apply(
                diff_path, patch_cwd, str(resolved), clearance=clearance,
            )
        except (CapabilityDenied, ExecutorError) as e:
            return DiffResult(
                success=False, file=str(resolved), applied=False,
                stdout="", stderr="", error=str(e),
            )
        except Exception as e:
            return DiffResult(
                success=False, file=str(resolved), applied=False,
                stdout="", stderr="", error=str(e),
            )
        finally:
            diff_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # run_task
    # ------------------------------------------------------------------

    def run_task(
        self,
        working_dir: Path,
        command: str,
        *,
        timeout_s: int = 60,
        env: dict[str, str] | None = None,
        clearance: str | None = None,
    ) -> TaskResult:
        """Ejecuta un comando en el directorio del proyecto."""
        resolved = working_dir.expanduser().resolve()
        if not resolved.exists():
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=0,
                error=f"Directorio no existe: {resolved}",
            )

        if env:
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=0,
                error="env custom no soportado por AtlasExecutor en Gate F",
            )

        start = time.perf_counter()
        try:
            parts = shlex.split(command)
            if not parts:
                return TaskResult(
                    success=False, command=command, working_dir=str(resolved),
                    stdout="", stderr="", exit_code=-1, duration_ms=0,
                    error="Comando vacio",
                )
            cap = self._executor.issuer.issue_exec(
                parts[0],
                args=tuple(parts[1:]),
                clearance=clearance,
                working_dir=resolved,
                timeout_s=timeout_s,
            )
            result = self._executor.execute_exec(cap)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return TaskResult(
                success=result.success,
                command=command,
                working_dir=str(resolved),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                duration_ms=duration_ms,
            )
        except (CapabilityDenied, ExecutorError) as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=duration_ms,
                error=str(e),
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=duration_ms,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _build_default_executor(self, workspace: Path) -> AtlasExecutor:
        config_path = self._resolve_permissions_config()
        profile = PermissionProfile(config_path=config_path, workspace=workspace)
        merkle = MerkleLogger(workspace / "logs")
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        from atlas.security.capabilities import CapabilityIssuer  # noqa: PLC0415

        return AtlasExecutor(
            issuer=CapabilityIssuer(profile),
            merkle=merkle,
            sandbox=sandbox,
        )

    def _resolve_permissions_config(self) -> Path:
        from atlas.runtime_paths import atlas_data_root

        candidates = [
            Path.cwd() / "config" / "permissions.yaml",
            atlas_data_root() / "config" / "permissions.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("No se encontro config/permissions.yaml")

    def _write_tmp_diff(self, diff_text: str) -> Path:
        tmp_dir = self._workspace / "tmp" / "editor_diffs"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        diff_path = tmp_dir / f"diff_{time.time_ns()}.patch"
        cap = self._executor.issuer.issue_write(
            diff_path,
            max_bytes=max(len(diff_text.encode("utf-8")), 1),
        )
        self._executor.execute_write(cap, diff_text.encode("utf-8"))
        return diff_path

    def _try_patch_apply(
        self,
        diff_path: Path,
        working_dir: Path,
        target_file: str,
        *,
        clearance: str | None = None,
    ) -> DiffResult:
        patch_binary = shutil.which("patch")
        if patch_binary is None:
            return DiffResult(
                success=False,
                file=target_file,
                applied=False,
                stdout="",
                stderr="",
                error="El comando patch no esta disponible en el sistema.",
            )

        last_result = None
        for strip_arg in ("-p1", "-p0"):
            try:
                cap = self._executor.issuer.issue_exec(
                    "patch",
                    args=(strip_arg, "--input", str(diff_path)),
                    working_dir=working_dir,
                    timeout_s=10,
                    clearance=clearance,
                )
            except CapabilityDenied as e:
                return DiffResult(
                    success=False, file=target_file, applied=False,
                    stdout="", stderr="", error=str(e),
                )

            last_result = self._executor.execute_exec(cap)
            if last_result.exit_code == 0:
                return DiffResult(
                    success=True, file=target_file, applied=True,
                    stdout=last_result.stdout, stderr=last_result.stderr,
                )

        if last_result is None:
            return DiffResult(
                success=False,
                file=target_file,
                applied=False,
                stdout="",
                stderr="",
                error="No se pudo ejecutar patch.",
            )

        return DiffResult(
            success=False,
            file=target_file,
            applied=False,
            stdout=last_result.stdout,
            stderr=last_result.stderr,
            error=f"patch fallo: {last_result.stderr[:500]}",
        )

    def _get_version(self, binary: str) -> str | None:
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:100]
            return None
        except Exception:
            return None

    def _find_git_dir(self, path: Path) -> Path | None:
        """Busca el directorio raiz de un repositorio git."""
        current = path.expanduser().resolve().parent
        for _ in range(10):  # max 10 niveles hacia arriba
            git_dir = current / ".git"
            if git_dir.exists():
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None
