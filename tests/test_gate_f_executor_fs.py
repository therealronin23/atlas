"""Tests for GateFExecutor.run_read_external_file."""
from pathlib import Path

import pytest

from atlas.core.orchestrator_parts.gate_f_executor import GateFExecutor
from atlas.security.external_fs_bridge import ExternalFsBridge


@pytest.fixture
def gfe(tmp_path: Path) -> GateFExecutor:
    """Create a minimal GateFExecutor with stubbed dependencies."""
    return GateFExecutor(
        workspace=tmp_path,
        executor=None,
        ssrf_bridge=None,
        merkle=None,
        gate_h=None,
        timetravel=lambda: None,
        bus=None,
        check_gate_h_allowed=lambda *a: None,
        record_receipt=lambda *a, **k: None,
        thermal_blocks=lambda: None,
    )


class TestRunReadExternalFile:
    """Test suite for GateFExecutor.run_read_external_file."""

    def test_file_inside_allowed_root(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 1: File inside an allowed extra_root reads successfully."""
        # Create a test file inside tmp_path
        test_file = tmp_path / "test_file.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content, encoding="utf-8")

        # Override the fs_bridge with one that has tmp_path as an extra root
        gfe._fs_bridge = ExternalFsBridge(extra_roots={str(tmp_path)})

        result = gfe.run_read_external_file(str(test_file))

        assert result["path"] == str(test_file)
        assert result["allowed"] is True
        assert result["resolved_path"] == str(test_file.resolve())
        assert result["content"] == test_content
        assert result["error"] is None

    def test_file_outside_any_root_fail_closed(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 2: File outside any root (default bridge, no extra_roots) is denied."""
        # Create a file outside tmp_path (use a sibling directory)
        outside_dir = tmp_path.parent / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "outside_file.txt"
        outside_file.write_text("Should not be readable", encoding="utf-8")

        # Ensure the default fs_bridge has no extra_roots (fail-closed)
        gfe._fs_bridge = ExternalFsBridge()

        result = gfe.run_read_external_file(str(outside_file))

        assert result["path"] == str(outside_file)
        assert result["allowed"] is False
        assert result["content"] == ""
        assert result["error"] != ""
        assert result["error"] is not None

    def test_nonexistent_file_inside_allowed_root(self, gfe: GateFExecutor, tmp_path: Path) -> None:
        """Case 3: Non-existent file inside an allowed root returns allowed=True but error."""
        # Path to a non-existent file inside tmp_path
        nonexistent_file = tmp_path / "nonexistent_file.txt"

        # Override the fs_bridge with one that has tmp_path as an extra root
        gfe._fs_bridge = ExternalFsBridge(extra_roots={str(tmp_path)})

        result = gfe.run_read_external_file(str(nonexistent_file))

        assert result["path"] == str(nonexistent_file)
        assert result["allowed"] is True
        assert result["resolved_path"] == str(nonexistent_file.resolve())
        assert result["content"] == ""
        assert result["error"] != ""
        assert result["error"] is not None
        # Verify the error is an OSError (file not found)
        assert "No such file or directory" in result["error"] or "FileNotFoundError" in result["error"]
