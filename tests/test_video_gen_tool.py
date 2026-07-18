"""
Tests del Video Generation Tool (absorbido de Hermes-Agent, 2026-07-18).

Misma disciplina que test_image_gen_tool.py: mockea el SDK fal_client (nunca
la API real — cuesta dinero y tarda minutos), output_path pasa por
ExternalFsBridge, credencial explícita, auditoría Merkle.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge
from atlas.tools.video_gen_tool import VideoGenTool


class TestGovernance:
    def test_output_outside_any_root_raises(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside" / "out.mp4"
        bridge = ExternalFsBridge(extra_roots={str(allowed)})
        tool = VideoGenTool(fs_bridge=bridge)

        with pytest.raises(PermissionError, match="output_path"):
            tool.generate("a fox running", str(outside))

    def test_invalid_aspect_ratio_fails_without_calling_fal(self, tmp_path: Path) -> None:
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe") as fal_mock:
            result = tool.generate(
                "a fox running", str(tmp_path / "out.mp4"), aspect_ratio="21:9",
            )
        assert not result.success
        assert "aspect_ratio" in (result.error or "")
        fal_mock.assert_not_called()


class TestGenerateMocked:
    def test_missing_api_key_returns_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FAL_KEY", raising=False)
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge)

        result = tool.generate("a fox running", str(tmp_path / "out.mp4"))
        assert not result.success
        assert "FAL_KEY" in (result.error or "")

    def test_successful_generation_writes_file_and_returns_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge)
        out = tmp_path / "out.mp4"

        with patch.object(
            tool, "_fal_subscribe",
            return_value={"video": {"url": "https://fal.media/fake/out.mp4"}},
        ), patch.object(tool, "_download", return_value=b"fake mp4 bytes"):
            result = tool.generate("a fox running", str(out))

        assert result.success
        assert result.video_url == "https://fal.media/fake/out.mp4"
        assert out.read_bytes() == b"fake mp4 bytes"

    def test_missing_video_key_is_a_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe", return_value={}):
            result = tool.generate("a fox running", str(tmp_path / "out.mp4"))

        assert not result.success
        assert "no devolvió vídeo" in (result.error or "")

    def test_fal_exception_returns_failed_result_not_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe", side_effect=RuntimeError("fal.ai unreachable")):
            result = tool.generate("a fox running", str(tmp_path / "out.mp4"))

        assert not result.success
        assert "fal.ai unreachable" in (result.error or "")


class TestMerkleAudit:
    def test_logs_success_to_merkle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = VideoGenTool(fs_bridge=bridge, merkle=merkle)

        with patch.object(
            tool, "_fal_subscribe",
            return_value={"video": {"url": "https://fal.media/fake/out.mp4"}},
        ), patch.object(tool, "_download", return_value=b"bytes"):
            tool.generate("a fox running", str(tmp_path / "out.mp4"))

        entries = list(merkle.tail(5))
        assert any(e.action == "video_gen.generate" and e.result == "ok" for e in entries)
