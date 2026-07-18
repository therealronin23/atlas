"""
Tests del Image Generation Tool (absorbido de Hermes-Agent, 2026-07-18).

Misma disciplina que test_stirling_pdf_tool.py: mockea la llamada al SDK
fal_client (nunca la API real — cuesta dinero), output_path pasa por
ExternalFsBridge, credencial explícita, auditoría Merkle.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge
from atlas.tools.image_gen_tool import ImageGenTool


class TestGovernance:
    def test_output_outside_any_root_raises(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside" / "out.png"
        bridge = ExternalFsBridge(extra_roots={str(allowed)})
        tool = ImageGenTool(fs_bridge=bridge)

        with pytest.raises(PermissionError, match="output_path"):
            tool.generate("a red fox", str(outside))

    def test_invalid_aspect_ratio_fails_without_calling_fal(self, tmp_path: Path) -> None:
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe") as fal_mock:
            result = tool.generate(
                "a red fox", str(tmp_path / "out.png"), aspect_ratio="ultrawide",
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
        tool = ImageGenTool(fs_bridge=bridge)

        result = tool.generate("a red fox", str(tmp_path / "out.png"))
        assert not result.success
        assert "FAL_KEY" in (result.error or "")

    def test_successful_generation_writes_file_and_returns_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge)
        out = tmp_path / "out.png"

        with patch.object(
            tool, "_fal_subscribe",
            return_value={"images": [{"url": "https://fal.media/fake/out.png"}]},
        ), patch.object(tool, "_download", return_value=b"\x89PNG fake bytes"):
            result = tool.generate("a red fox", str(out), model="fal-ai/flux/dev")

        assert result.success
        assert result.image_url == "https://fal.media/fake/out.png"
        assert result.bytes_written == len(b"\x89PNG fake bytes")
        assert out.read_bytes() == b"\x89PNG fake bytes"

    def test_data_uri_image_decoded_without_network_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import base64

        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge)
        raw = b"tiny-fake-png-bytes"
        data_uri = "data:image/png;base64," + base64.b64encode(raw).decode()

        with patch.object(
            tool, "_fal_subscribe", return_value={"images": [{"url": data_uri}]},
        ):
            result = tool.generate("a red fox", str(tmp_path / "out.png"))

        assert result.success
        assert (tmp_path / "out.png").read_bytes() == raw

    def test_empty_images_list_is_a_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe", return_value={"images": []}):
            result = tool.generate("a red fox", str(tmp_path / "out.png"))

        assert not result.success
        assert "no devolvió imágenes" in (result.error or "")

    def test_fal_exception_returns_failed_result_not_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge)

        with patch.object(tool, "_fal_subscribe", side_effect=RuntimeError("fal.ai unreachable")):
            result = tool.generate("a red fox", str(tmp_path / "out.png"))

        assert not result.success
        assert "fal.ai unreachable" in (result.error or "")


class TestMerkleAudit:
    def test_logs_success_to_merkle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAL_KEY", "fake-key-for-test")
        merkle = MerkleLogger(log_dir=tmp_path / "merkle")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = ImageGenTool(fs_bridge=bridge, merkle=merkle)

        with patch.object(
            tool, "_fal_subscribe",
            return_value={"images": [{"url": "https://fal.media/fake/out.png"}]},
        ), patch.object(tool, "_download", return_value=b"bytes"):
            tool.generate("a red fox", str(tmp_path / "out.png"))

        entries = list(merkle.tail(5))
        assert any(e.action == "image_gen.generate" and e.result == "ok" for e in entries)
