"""
Tests del Crawler Tool (scraping absorbido de Crawl4AI, 2026-07-02).

Misma disciplina que test_browser.py: SSRF Bridge antes de tocar la red,
bloqueo de red privada salvo opt-in, y auditoría Merkle. La mayoría mockea
`subprocess.run` (rápido, no depende de que `.venv-scraping` exista); un test
E2E marcado `computer_use` corre el worker real contra un servidor HTTP local.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge
from atlas.tools.crawler import CrawlerTool


@pytest.fixture
def bridge_with_localhost() -> SSRFBridge:
    return SSRFBridge(extra_allowed={"127.0.0.1"}, allow_private_network=True)


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    return p


@pytest.fixture
def crawler(tmp_path: Path, bridge_with_localhost: SSRFBridge) -> CrawlerTool:
    fake_python = _touch(tmp_path / "fake-python")
    return CrawlerTool(
        workspace=tmp_path, bridge=bridge_with_localhost, allow_private_network=True,
        python_bin=fake_python,  # is_available=True para tests mockeados
    )


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestGovernance:
    def test_blocked_url_raises_permission_error(self, tmp_path: Path) -> None:
        ct = CrawlerTool(workspace=tmp_path, bridge=SSRFBridge())
        with pytest.raises(PermissionError, match="SSRF Bridge"):
            ct.crawl("https://evil-not-allowlisted.example")

    def test_private_ip_blocked_without_opt_in(
        self, tmp_path: Path, bridge_with_localhost: SSRFBridge
    ) -> None:
        # bridge_with_localhost ya permite 127.0.0.1 (allow_private_network=True
        # a nivel de bridge); CrawlerTool debe seguir exigiendo SU PROPIO
        # allow_private_network=True (defensa en dos capas, igual que BrowserTool).
        ct = CrawlerTool(
            workspace=tmp_path, bridge=bridge_with_localhost, allow_private_network=False,
        )
        with pytest.raises(PermissionError, match="allow_private_network"):
            ct.crawl("http://127.0.0.1:9/x")

    def test_missing_venv_returns_failed_result_not_exception(
        self, tmp_path: Path, bridge_with_localhost: SSRFBridge
    ) -> None:
        ct = CrawlerTool(
            workspace=tmp_path, bridge=bridge_with_localhost,
            allow_private_network=True, python_bin=tmp_path / "does-not-exist",
        )
        result = ct.crawl("http://127.0.0.1:9/x")
        assert result.success is False
        assert "venv aislado" in (result.error or "")


class TestCrawlMocked:
    def test_success_parses_worker_json(self, crawler: CrawlerTool) -> None:
        payload = json.dumps({"success": True, "status_code": 200, "markdown": "# Hi", "error": None})
        with patch("subprocess.run", return_value=_FakeProc(stdout=payload)) as m:
            result = crawler.crawl("http://127.0.0.1:9/x")
        assert result.success is True
        assert result.status_code == 200
        assert result.markdown == "# Hi"
        assert m.call_count == 1

    def test_worker_reported_failure_propagates(self, crawler: CrawlerTool) -> None:
        payload = json.dumps({"success": False, "status_code": None, "markdown": "", "error": "net::ERR_CONNECTION_RESET"})
        with patch("subprocess.run", return_value=_FakeProc(stdout=payload)):
            result = crawler.crawl("http://127.0.0.1:9/x")
        assert result.success is False
        assert "ERR_CONNECTION_RESET" in (result.error or "")

    def test_timeout_returns_failed_result_not_exception(self, crawler: CrawlerTool) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            result = crawler.crawl("http://127.0.0.1:9/x")
        assert result.success is False
        assert result.error == "timeout"

    def test_malformed_worker_output_fails_closed(self, crawler: CrawlerTool) -> None:
        with patch("subprocess.run", return_value=_FakeProc(stdout="not json", stderr="traceback...")):
            result = crawler.crawl("http://127.0.0.1:9/x")
        assert result.success is False
        assert result.error is not None

    def test_audits_success_and_failure_via_merkle(
        self, tmp_path: Path, bridge_with_localhost: SSRFBridge
    ) -> None:
        merkle = MerkleLogger(tmp_path / "logs")
        ct = CrawlerTool(
            workspace=tmp_path, bridge=bridge_with_localhost, allow_private_network=True,
            python_bin=_touch(tmp_path / "fake-python"), merkle=merkle,
        )
        with patch("subprocess.run", return_value=_FakeProc(stdout=json.dumps(
            {"success": True, "status_code": 200, "markdown": "hi", "error": None}
        ))):
            ct.crawl("http://127.0.0.1:9/x")
        records = [r for r in merkle.tail(10) if r.action == "crawler.crawl"]
        assert records
        assert records[-1].result == "ok"
        assert records[-1].payload["status_code"] == 200


# ---------------------------------------------------------------------------
# E2E real: worker de verdad, contra un servidor HTTP local (sin internet)
# ---------------------------------------------------------------------------

pytestmark_e2e = pytest.mark.computer_use


class _StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str = "/tmp", **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, *_: Any) -> None:
        pass


@pytest.fixture
def local_server(tmp_path: Path) -> Generator[str, None, None]:
    d = tmp_path / "www"
    d.mkdir()
    # Crawl4AI marca como "Blocked by anti-bot protection" cualquier respuesta
    # 200 con contenido casi vacío (su heurística anti-bot, no un bug nuestro) —
    # la página de prueba necesita tamaño realista para no disparar ese falso
    # positivo.
    body = "<p>Atlas Crawl Test paragraph.</p>\n" * 20
    (d / "index.html").write_text(f"<html><body><h1>Atlas Crawl Test</h1>{body}</body></html>")
    handler = lambda *a, **kw: _StaticHandler(*a, directory=str(d), **kw)  # noqa: E731
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/index.html"
    server.shutdown()


@pytest.mark.computer_use
def test_real_worker_crawls_local_server(
    tmp_path: Path, bridge_with_localhost: SSRFBridge, local_server: str
) -> None:
    scraping_python = Path(__file__).resolve().parent.parent / ".venv-scraping" / "bin" / "python3"
    if not scraping_python.is_file():
        pytest.skip(".venv-scraping no instalado — ver docstring de crawler.py")
    ct = CrawlerTool(
        workspace=tmp_path, bridge=bridge_with_localhost, allow_private_network=True,
        python_bin=scraping_python,
    )
    result = ct.crawl(local_server, max_chars=500)
    assert result.success is True
    assert "Atlas Crawl Test" in result.markdown
