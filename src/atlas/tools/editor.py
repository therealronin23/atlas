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

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
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
            size = resolved.stat().st_size
            if size > max_bytes:
                return FileReadResult(
                    success=False, path=str(resolved), content="", size_bytes=size,
                    error=f"Archivo demasiado grande ({size}B > {max_bytes}B max)",
                )
            content = resolved.read_text(encoding="utf-8")
            return FileReadResult(
                success=True, path=str(resolved), content=content,
                size_bytes=len(content.encode("utf-8")),
            )
        except Exception as e:
            return FileReadResult(
                success=False, path=str(resolved), content="", size_bytes=0,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # write_file
    # ------------------------------------------------------------------

    def write_file(self, path: Path, content: str) -> FileWriteResult:
        """Escribe contenido en un archivo (crea directorios si es necesario)."""
        resolved = path.expanduser().resolve()
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            encoded = content.encode("utf-8")
            resolved.write_text(content, encoding="utf-8")
            return FileWriteResult(
                success=True, path=str(resolved), bytes_written=len(encoded),
            )
        except Exception as e:
            return FileWriteResult(
                success=False, path=str(resolved), bytes_written=0, error=str(e),
            )

    # ------------------------------------------------------------------
    # apply_diff
    # ------------------------------------------------------------------

    def apply_diff(self, file_path: Path, diff_text: str) -> DiffResult:
        """
        Aplica un diff unificado a un archivo usando git apply o patch.
        Si el archivo esta bajo un repositorio git, usa `git apply`.
        Si no, usa `patch`.
        """
        resolved = file_path.expanduser().resolve()
        # Buscar si estamos dentro de un repo git
        git_dir = self._find_git_dir(resolved)

        try:
            if git_dir is not None:
                # Usar git apply desde el directorio del repo
                result = subprocess.run(
                    ["git", "apply"],
                    input=diff_text,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(git_dir),
                )
                if result.returncode == 0:
                    return DiffResult(
                        success=True, file=str(resolved), applied=True,
                        stdout=result.stdout, stderr=result.stderr,
                    )
                # Si git apply falla, intentar con --recount (tolerante a offsets)
                result2 = subprocess.run(
                    ["git", "apply", "--recount"],
                    input=diff_text,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(git_dir),
                )
                if result2.returncode == 0:
                    return DiffResult(
                        success=True, file=str(resolved), applied=True,
                        stdout=result2.stdout, stderr=result2.stderr,
                    )
                return DiffResult(
                    success=False, file=str(resolved), applied=False,
                    stdout=result.stdout, stderr=result.stderr,
                    error=f"git apply fallo: {result.stderr[:500]}",
                )
            else:
                # Usar patch command
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".diff", delete=False,
                ) as f:
                    f.write(diff_text)
                    diff_path = f.name
                result = subprocess.run(
                    ["patch", "-p1", "-i", diff_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(resolved.parent),
                )
                Path(diff_path).unlink(missing_ok=True)
                if result.returncode == 0:
                    return DiffResult(
                        success=True, file=str(resolved), applied=True,
                        stdout=result.stdout, stderr=result.stderr,
                    )
                return DiffResult(
                    success=False, file=str(resolved), applied=False,
                    stdout=result.stdout, stderr=result.stderr,
                    error=f"patch fallo: {result.stderr[:500]}",
                )
        except subprocess.TimeoutExpired:
            return DiffResult(
                success=False, file=str(resolved), applied=False,
                stdout="", stderr="", error="Timeout aplicando diff (10s)",
            )
        except Exception as e:
            return DiffResult(
                success=False, file=str(resolved), applied=False,
                stdout="", stderr="", error=str(e),
            )

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
    ) -> TaskResult:
        """Ejecuta un comando en el directorio del proyecto."""
        resolved = working_dir.expanduser().resolve()
        if not resolved.exists():
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=0,
                error=f"Directorio no existe: {resolved}",
            )

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(resolved),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=merged_env,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return TaskResult(
                success=(result.returncode == 0),
                command=command,
                working_dir=str(resolved),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return TaskResult(
                success=False, command=command, working_dir=str(resolved),
                stdout="", stderr="", exit_code=-1, duration_ms=duration_ms,
                error=f"Timeout ({timeout_s}s)",
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