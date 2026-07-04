"""
Tests del Stirling PDF Tool (manipulación de PDF self-hosted, 2026-07-03).

Misma disciplina que test_crawler.py: mockea la llamada HTTP (nunca el servicio
real), input_path Y output_path pasan por ExternalFsBridge, credencial
explícita, auditoría Merkle.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge
from atlas.tools.stirling_pdf_tool import StirlingPdfTool


def _touch(p: Path, content: bytes = b"dummy pdf bytes") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


class _FakeResponse:
    def __init__(self, status: int, data: bytes) -> None:
        self.status = status
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestGovernance:
    def test_input_outside_any_root_raises(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = _touch(tmp_path / "outside" / "in.pdf")
        bridge = ExternalFsBridge(extra_roots={str(allowed)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        with pytest.raises(PermissionError, match="input_path"):
            tool.run_operation("general/rotate-pdf", str(outside), str(allowed / "out.pdf"))

    def test_output_outside_any_root_raises(self, tmp_path: Path) -> None:
        allowed_in = tmp_path / "allowed_in"
        allowed_in.mkdir()
        in_file = _touch(allowed_in / "in.pdf")
        outside_out = tmp_path / "outside" / "out.pdf"
        # bridge solo permite el root de entrada, no el de salida
        bridge = ExternalFsBridge(extra_roots={str(allowed_in)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        with pytest.raises(PermissionError, match="output_path"):
            tool.run_operation("general/rotate-pdf", str(in_file), str(outside_out))


class TestRunOperationMocked:
    def test_missing_api_key_returns_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STIRLING_PDF_API_KEY", raising=False)
        in_file = _touch(tmp_path / "in.pdf")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        result = tool.run_operation("general/rotate-pdf", str(in_file), str(tmp_path / "out.pdf"))
        assert result.success is False
        assert "STIRLING_PDF_API_KEY" in (result.error or "")

    def test_success_writes_output_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STIRLING_PDF_API_KEY", "fake-key")
        in_file = _touch(tmp_path / "in.pdf")
        out_file = tmp_path / "out.pdf"
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        fake_bytes = b"%PDF-1.6 fake rotated content"
        with patch("urllib.request.urlopen", return_value=_FakeResponse(200, fake_bytes)):
            result = tool.run_operation(
                "general/rotate-pdf", str(in_file), str(out_file), angle="90",
            )

        assert result.success is True
        assert result.bytes_written == len(fake_bytes)
        assert result.error is None
        assert out_file.read_bytes() == fake_bytes

    def test_http_error_returns_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STIRLING_PDF_API_KEY", "fake-key")
        in_file = _touch(tmp_path / "in.pdf")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        from email.message import Message

        err = urllib.error.HTTPError(
            url="http://x", code=400, msg="Bad Request", hdrs=Message(),
            fp=MagicMock(read=lambda: b"bad input"),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            result = tool.run_operation("general/rotate-pdf", str(in_file), str(tmp_path / "out.pdf"))

        assert result.success is False
        assert "400" in (result.error or "")

    def test_timeout_returns_failed_result_not_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STIRLING_PDF_API_KEY", "fake-key")
        in_file = _touch(tmp_path / "in.pdf")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = tool.run_operation("general/rotate-pdf", str(in_file), str(tmp_path / "out.pdf"))

        assert result.success is False
        assert result.error is not None

    def test_non_200_status_returns_failed_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STIRLING_PDF_API_KEY", "fake-key")
        in_file = _touch(tmp_path / "in.pdf")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge)

        with patch("urllib.request.urlopen", return_value=_FakeResponse(202, b"")):
            result = tool.run_operation("general/rotate-pdf", str(in_file), str(tmp_path / "out.pdf"))

        assert result.success is False

    def test_audits_success_via_merkle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STIRLING_PDF_API_KEY", "fake-key")
        in_file = _touch(tmp_path / "in.pdf")
        merkle = MerkleLogger(tmp_path / "logs")
        bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
        tool = StirlingPdfTool(fs_bridge=bridge, merkle=merkle)

        with patch("urllib.request.urlopen", return_value=_FakeResponse(200, b"content")):
            tool.run_operation("general/rotate-pdf", str(in_file), str(tmp_path / "out.pdf"))

        records = [r for r in merkle.tail(10) if r.action == "stirling_pdf.run_operation"]
        assert records
        assert records[-1].result == "ok"
