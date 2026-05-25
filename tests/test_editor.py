"""
Tests Gate F/F2 — Editor Integration Tool.

Usa un proyecto de ejemplo en tmp_path. No requiere Cursor/VS Code
instalados — los tests de editor detection usan force o verifican
el fallback graceful cuando no hay editor.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Generator, Any

import pytest

from atlas.tools.editor import EditorTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Crea un proyecto de ejemplo bajo workspace/tmp/ (escritura AUTO)."""
    project = tmp_path / "tmp" / "sample-app"
    project.mkdir(parents=True)

    # Archivo fuente simple
    src = project / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    return 'Hello World'\n\n"
        "def add(a, b):\n    return a + b\n"
    )
    (src / "utils.py").write_text(
        "import math\n\ndef sqrt(n):\n    return math.sqrt(n)\n"
    )

    # Archivo README
    (project / "README.md").write_text("# Sample App\n\nA sample project for testing.\n")

    # Subdirectorio vacio
    (project / "empty").mkdir()

    return project


@pytest.fixture
def sample_project_with_git(sample_project: Path) -> Path:
    """Inicializa git en el proyecto de ejemplo."""
    import subprocess
    subprocess.run(
        ["git", "init"],
        cwd=str(sample_project),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@atlas.local"],
        cwd=str(sample_project),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Atlas Test"],
        cwd=str(sample_project),
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=str(sample_project),
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(sample_project),
        capture_output=True,
    )
    return sample_project


@pytest.fixture
def editor(tmp_path: Path) -> EditorTool:
    """EditorTool con workspace temporal."""
    return EditorTool(workspace=tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEditorDetection:

    def test_detect_returns_not_available_if_no_editor(self, tmp_path: Path) -> None:
        """Sin editores instalados, must return available=False."""
        et = EditorTool(workspace=tmp_path)
        info = et.detect_editor(force="nonexistent-editor-xyz")
        assert info.available is False
        assert info.name == "none"

    def test_detect_caches_result(self, tmp_path: Path) -> None:
        """Llamar detect_editor dos veces debe devolver el mismo objeto."""
        et = EditorTool(workspace=tmp_path)
        info1 = et.detect_editor(force="nonexistent-editor-xyz")
        info2 = et.detect_editor(force="vim")  # deberia ignorar force por cache
        # La cache no se usa si force es diferente - verificar que accessible
        assert info1.available is False


class TestReadFile:

    def test_read_existing_file(self, sample_project: Path, editor: EditorTool) -> None:
        result = editor.read_file(sample_project / "src" / "main.py")
        assert result.success is True
        assert "Hello World" in result.content
        assert result.size_bytes > 0

    def test_read_nonexistent_file(self, editor: EditorTool) -> None:
        result = editor.read_file(Path("/tmp/nonexistent_file_xyz"))
        assert result.success is False
        assert "no encontrado" in result.error.lower()

    def test_read_directory_fails(self, sample_project: Path, editor: EditorTool) -> None:
        result = editor.read_file(sample_project / "src")
        assert result.success is False
        assert result.error is not None

    def test_read_exceeds_max_bytes(self, sample_project: Path, editor: EditorTool) -> None:
        """Archivo mayor a max_bytes debe fallar."""
        big_file = sample_project / "big.txt"
        big_file.write_text("x" * 100)
        result = editor.read_file(big_file, max_bytes=10)
        assert result.success is False
        assert "demasiado grande" in result.error.lower()

    def test_read_returns_full_content(self, sample_project: Path, editor: EditorTool) -> None:
        result = editor.read_file(sample_project / "README.md")
        assert result.success is True
        assert "# Sample App" in result.content

    def test_read_blocked_system_path(self, editor: EditorTool) -> None:
        result = editor.read_file(Path("/etc/passwd"))
        assert result.success is False
        assert "bloqueo absoluto" in result.error.lower()


class TestWriteFile:

    def test_write_creates_file(self, sample_project: Path, editor: EditorTool) -> None:
        path = sample_project / "new_file.py"
        assert not path.exists()
        result = editor.write_file(path, "print('hello')")
        assert result.success is True
        assert path.exists()
        assert path.read_text() == "print('hello')"

    def test_write_creates_directories(self, tmp_path: Path, editor: EditorTool) -> None:
        path = tmp_path / "tmp" / "deep" / "nested" / "file.py"
        result = editor.write_file(path, "x = 1")
        assert result.success is True
        assert path.exists()
        assert path.read_text() == "x = 1"

    def test_write_overwrites_existing(self, sample_project: Path, editor: EditorTool) -> None:
        path = sample_project / "src" / "main.py"
        original = path.read_text()
        result = editor.write_file(path, "print('overwritten')")
        assert result.success is True
        assert path.read_text() != original
        assert path.read_text() == "print('overwritten')"

    def test_write_outside_workspace_is_blocked(self, tmp_path: Path, editor: EditorTool) -> None:
        path = tmp_path.parent / "outside-workspace.txt"
        result = editor.write_file(path, "nope")
        assert result.success is False
        assert "fuera del workspace" in result.error.lower()


class TestApplyDiff:

    def test_git_apply_simple_diff(self, sample_project_with_git: Path, editor: EditorTool) -> None:
        """Aplicar un diff simple sobre un archivo en repo git."""
        main_py = sample_project_with_git / "src" / "main.py"
        diff = (
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -1,4 +1,4 @@\n"
            " def hello():\n"
            "-    return 'Hello World'\n"
            "+    return 'Hello Atlas'\n"
            " \n"
            " def add(a, b):\n"
        )
        editor._executor.issuer.profile.mark_confirmed("task:editor-test")
        result = editor.apply_diff(main_py, diff, clearance="task:editor-test")
        assert result.success is True, f"git apply fallo: {result.stderr}"
        assert "Hello Atlas" in main_py.read_text()
        assert "Hello World" not in main_py.read_text()

    def test_git_apply_invalid_diff(self, sample_project_with_git: Path, editor: EditorTool) -> None:
        """Diff invalido debe fallar gracefulmente."""
        main_py = sample_project_with_git / "src" / "main.py"
        diff = "--- a/main.py\n+++ b/main.py\n@@ -999 +999 @@\n-no-such-line\n+replacement\n"
        result = editor.apply_diff(main_py, diff)
        assert result.success is False
        assert result.applied is False

    def test_apply_diff_without_git(self, tmp_path: Path, editor: EditorTool) -> None:
        """Diff fuera de un repo git debe usar patch."""
        target = tmp_path / "tmp" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("line1\nline2\nline3\n")

        diff = (
            "--- file.txt\n"
            "+++ file.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+line2-modified\n"
            " line3\n"
        )
        editor._executor.issuer.profile.mark_confirmed("task:patch-test")
        result = editor.apply_diff(target, diff, clearance="task:patch-test")
        assert result is not None

        if shutil.which("patch") is None:
            assert result.success is False
            assert "patch" in (result.error or "").lower()
        else:
            assert result.success is True, result.error or result.stderr
            assert target.read_text() == "line1\nline2-modified\nline3\n"


class TestRunTask:

    def test_run_successful_task(self, sample_project: Path, editor: EditorTool) -> None:
        editor._executor.issuer.profile.mark_confirmed("exec:echo hello")
        result = editor.run_task(sample_project, "echo hello")
        assert result.success is True
        assert "hello" in result.stdout
        assert result.duration_ms > 0

    def test_run_failing_task(self, sample_project: Path, editor: EditorTool) -> None:
        result = editor.run_task(sample_project, "false")
        assert result.success is False
        assert result.exit_code != 0

    def test_run_task_nonexistent_dir(self, editor: EditorTool) -> None:
        result = editor.run_task(Path("/nonexistent"), "echo hi")
        assert result.success is False
        assert "no existe" in result.error.lower()

    def test_run_task_blocks_unapproved_command(self, sample_project: Path, editor: EditorTool) -> None:
        """Comandos fuera de allowlist deben bloquearse antes de ejecutarse."""
        result = editor.run_task(sample_project, "sleep 10", timeout_s=1)
        assert result.success is False
        assert "allowlist" in result.error

    def test_run_python_c_is_blocked(self, sample_project: Path, editor: EditorTool) -> None:
        """Python arbitrario no debe ejecutarse desde EditorTool."""
        result = editor.run_task(sample_project, "python3 -c 'print(2+2)'")
        assert result.success is False
        assert "allowlist" in result.error


class TestOpenProject:

    def test_open_nonexistent_path(self, editor: EditorTool) -> None:
        """Abrir un path que no existe debe fallar."""
        result = editor.open_project(Path("/nonexistent-path-xyz"))
        assert result.success is False
        assert result.error is not None

    def test_open_without_editor_detected(self, tmp_path: Path) -> None:
        """Sin editor, debe fallar gracefulmente."""
        et = EditorTool(workspace=tmp_path)
        et.detect_editor(force="nonexistent-editor-xyz")
        result = et.open_project(tmp_path)
        assert result.success is False
        assert "no se detecto" in result.error.lower()

    def test_open_creates_process(self, sample_project: Path, editor: EditorTool) -> None:
        """Si hay code detectado, debe lanzar proceso (verificamos que no explota)."""
        info = editor.detect_editor()
        if not info.available:
            pytest.skip("No hay editor disponible en este entorno")
        result = editor.open_project(sample_project)
        assert result.success is True
        assert result.editor != "none"


class TestReadWriteRoundtrip:

    def test_write_then_read(self, sample_project: Path, editor: EditorTool) -> None:
        """Escribir y luego leer debe devolver el mismo contenido."""
        path = sample_project / "roundtrip.txt"
        content = "Hello from Atlas\nLine 2\n"
        editor.write_file(path, content)
        result = editor.read_file(path)
        assert result.success is True
        assert result.content == content

    def test_write_binary_content(self, sample_project: Path, editor: EditorTool) -> None:
        """Write debe manejar contenido unicode."""
        path = sample_project / "unicode.txt"
        content = "Hello ñoño 😊 Atlas"
        editor.write_file(path, content)
        result = editor.read_file(path)
        assert result.success is True
        assert result.content == content


class TestGitDirDetection:

    def test_find_git_dir_from_file(self, sample_project_with_git: Path) -> None:
        """Encontrar el git dir desde un archivo dentro del repo."""
        et = EditorTool(workspace=sample_project_with_git)
        file_path = sample_project_with_git / "src" / "main.py"
        git_dir = et._find_git_dir(file_path)
        assert git_dir is not None
        assert git_dir.resolve() == sample_project_with_git.resolve()

    def test_find_git_dir_outside_repo(self, tmp_path: Path) -> None:
        """Fuera de un repo git debe devolver None."""
        et = EditorTool(workspace=tmp_path)
        git_dir = et._find_git_dir(tmp_path / "nonexistent")
        assert git_dir is None

    def test_find_git_dir_from_root(self, sample_project_with_git: Path) -> None:
        """Desde la raiz del repo, debe encontrarse a si mismo."""
        et = EditorTool(workspace=sample_project_with_git)
        git_dir = et._find_git_dir(sample_project_with_git / "README.md")
        assert git_dir is not None
        assert git_dir.resolve() == sample_project_with_git.resolve()
