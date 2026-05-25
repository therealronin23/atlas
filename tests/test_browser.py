"""
Tests Gate F/F1 — Browser Tool (Playwright).

Usa paginas HTML estaticas servidas por un mini servidor HTTP local.
No requiere internet real. El fixture http_server arranca un servidor
en un thread separado.

Si Playwright no esta instalado, los tests se skipean con un mensaje
claro de como instalarlo.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Generator

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge, DEFAULT_ALLOWED_DOMAINS
from atlas.tools.browser import BrowserTool


# ---------------------------------------------------------------------------
# Mini servidor HTTP estatico para los tests
# ---------------------------------------------------------------------------

class _StaticHandler(SimpleHTTPRequestHandler):
    """Sirve archivos desde un directorio temporal."""

    def __init__(self, *args: Any, directory: str = "/tmp", **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, *_: Any) -> None:
        pass  # Silenciar logs del servidor en tests


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """Crea un directorio con paginas HTML estaticas para los tests."""
    d = tmp_path / "www"
    d.mkdir()

    # Pagina simple
    (d / "index.html").write_text(
        "<html><head><title>Test Page</title></head>"
        "<body><h1>Hello Atlas</h1><p id='content'>Browser tool works</p>"
        "<form><input id='search' name='q' type='text'/>"
        "<button id='submit'>Go</button></form></body></html>"
    )

    # Pagina larga (para test de extraccion)
    (d / "long.html").write_text(
        "<html><head><title>Long Page</title></head><body>"
        + "".join(f"<p>Line {i}</p>" for i in range(50))
        + "</body></html>"
    )

    # Pagina con formulario
    (d / "form.html").write_text(
        "<html><head><title>Form Page</title></head><body>"
        "<form action='/submit' method='POST'>"
        "<input id='name' name='name' type='text'/>"
        "<input id='email' name='email' type='email'/>"
        "<button id='send'>Send</button>"
        "</form></body></html>"
    )

    return d


@pytest.fixture
def http_server(static_dir: Path) -> Generator[str, None, None]:
    """Arranca un servidor HTTP local en un thread daemon."""
    server = HTTPServer(
        ("127.0.0.1", 0),  # Puerto aleatorio
        lambda *a, **kw: _StaticHandler(*a, directory=str(static_dir), **kw),
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)  # Esperar a que arranque
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def bridge_with_localhost() -> SSRFBridge:
    """SSRF Bridge que permite 127.0.0.1 para tests."""
    return SSRFBridge(extra_allowed={"127.0.0.1"})


@pytest.fixture
def browser(tmp_path: Path, bridge_with_localhost: SSRFBridge) -> Generator[BrowserTool, None, None]:
    """BrowserTool con workspace temporal y bridge que permite localhost."""
    bt = BrowserTool(
        workspace=tmp_path,
        bridge=bridge_with_localhost,
        headless=True,
        allow_private_network=True,
    )
    yield bt
    try:
        bt.close()
    except Exception:
        pass


@pytest.fixture
def browser_with_merkle(tmp_path: Path, bridge_with_localhost: SSRFBridge) -> Generator[BrowserTool, None, None]:
    """BrowserTool configurado con MerkleLogger para verificar audit logging."""
    merkle_logger = MerkleLogger(tmp_path / "logs")
    bt = BrowserTool(
        workspace=tmp_path,
        bridge=bridge_with_localhost,
        headless=True,
        allow_private_network=True,
        merkle=merkle_logger,
    )
    yield bt
    try:
        bt.close()
    except Exception:
        pass


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "logs")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBrowserLifecycle:

    def test_launch_and_close(self, tmp_path: Path) -> None:
        """Lanzar y cerrar el browser no debe lanzar excepciones."""
        bt = BrowserTool(workspace=tmp_path, headless=True)
        bt.launch()
        assert bt.is_launched is True
        bt.close()
        assert bt.is_launched is False

    def test_double_launch_is_idempotent(self, tmp_path: Path) -> None:
        """Llamar launch() dos veces es idempotente."""
        bt = BrowserTool(workspace=tmp_path, headless=True)
        bt.launch()
        bt.launch()  # segunda llamada
        assert bt.is_launched is True
        bt.close()

    def test_browser_storage_state_is_saved_on_close(
        self,
        http_server: str,
        tmp_path: Path,
        bridge_with_localhost: SSRFBridge,
    ) -> None:
        bt = BrowserTool(
            workspace=tmp_path,
            bridge=bridge_with_localhost,
            headless=True,
            allow_private_network=True,
        )
        try:
            bt.navigate(http_server + "/index.html")
        finally:
            bt.close()

        storage_file = tmp_path / "tmp/browser_data/storage_state.json"
        assert storage_file.exists()
        assert storage_file.stat().st_size > 0
        data = json.loads(storage_file.read_text())
        assert isinstance(data, dict)

    def test_navigate_without_launch_auto_launches(self, http_server: str, browser: BrowserTool) -> None:
        """navigate() debe auto-lanzar el browser si no lo esta."""
        nav = browser.navigate(http_server + "/index.html")
        assert nav.status_code == 200
        assert browser.is_launched is True


class TestNavigation:

    def test_navigate_returns_title_and_text(self, http_server: str, browser: BrowserTool) -> None:
        nav = browser.navigate(http_server + "/index.html")
        assert nav.status_code == 200
        assert nav.title == "Test Page"
        assert "Hello Atlas" in nav.text
        assert "Browser tool works" in nav.text

    def test_navigate_to_invalid_url_raises(self, browser: BrowserTool) -> None:
        """URL bloqueada por SSRF Bridge debe lanzar PermissionError."""
        with pytest.raises(PermissionError, match="SSRF Bridge bloqueo"):
            browser.navigate("http://evil.com/malware")

    def test_navigate_returns_duration(self, http_server: str, browser: BrowserTool) -> None:
        nav = browser.navigate(http_server + "/index.html")
        assert nav.duration_ms > 0

    def test_navigate_to_long_page(self, http_server: str, browser: BrowserTool) -> None:
        """Pagina larga se trunca a 10k chars."""
        nav = browser.navigate(http_server + "/long.html")
        assert len(nav.text) <= 10000
        assert "Line 0" in nav.text

    def test_navigate_localhost_requires_allow_private_network(
        self,
        http_server: str,
        bridge_with_localhost: SSRFBridge,
        tmp_path: Path,
    ) -> None:
        bt = BrowserTool(
            workspace=tmp_path,
            bridge=bridge_with_localhost,
            headless=True,
            allow_private_network=False,
        )
        with pytest.raises(PermissionError, match="requiere allow_private_network"):
            bt.navigate(http_server + "/index.html")
        bt.close()

    def test_navigate_logs_to_merkle(self, http_server: str, browser_with_merkle: BrowserTool) -> None:
        browser_with_merkle.navigate(http_server + "/index.html")
        records = [r for r in browser_with_merkle._merkle.tail(10) if r.action == "browser.navigate"]
        assert records
        assert records[-1].result == "ok"
        assert records[-1].payload["status_code"] == 200


class TestScreenshot:

    def test_screenshot_creates_file(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/index.html")
        ss = browser.screenshot("test_shot")
        assert Path(ss.path).exists()
        assert ss.bytes_size > 0
        assert ss.width > 0

    def test_screenshot_without_navigate_raises(self, browser: BrowserTool) -> None:
        with pytest.raises(RuntimeError, match="no lanzado"):
            browser.screenshot()

    def test_screenshot_generates_auto_name(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/index.html")
        ss1 = browser.screenshot("alpha")
        import time
        time.sleep(0.01)
        ss2 = browser.screenshot("beta")
        assert ss1.path != ss2.path
        assert "alpha" in ss1.path
        assert "beta" in ss2.path


class TestFill:

    def test_fill_input(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/form.html")
        result = browser.fill("#name", "Atlas User")
        assert result.success is True
        assert result.value == "Atlas User"

    def test_fill_nonexistent_selector(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/form.html")
        result = browser.fill("#nonexistent", "value")
        assert result.success is False
        assert result.error is not None

    def test_fill_without_navigate_raises(self, browser: BrowserTool) -> None:
        with pytest.raises(RuntimeError):
            browser.fill("#x", "y")


class TestClick:

    def test_click_button(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/index.html")
        result = browser.click("#submit")
        assert result.success is True

    def test_click_nonexistent(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/index.html")
        result = browser.click("#does-not-exist")
        assert result.success is False
        assert result.error is not None


class TestExtract:

    def test_extract_after_navigate(self, http_server: str, browser: BrowserTool) -> None:
        browser.navigate(http_server + "/index.html")
        ext = browser.extract()
        assert ext.title == "Test Page"
        assert "Hello Atlas" in ext.text
        assert ext.url != ""

    def test_extract_without_navigate_raises(self, browser: BrowserTool) -> None:
        with pytest.raises(RuntimeError):
            browser.extract()


class TestSSRFBridge:

    def test_bridge_blocks_unknown_domain(self, browser: BrowserTool) -> None:
        with pytest.raises(PermissionError):
            browser.navigate("https://malware.example.com/exploit")

    def test_bridge_allows_known_domain(self, tmp_path: Path) -> None:
        """Un dominio en DEFAULT_ALLOWED_DOMAINS debe pasar."""
        bridge = SSRFBridge()
        # Elegimos un dominio que sabemos que esta en DEFAULT_ALLOWED_DOMAINS
        assert "api.github.com" in DEFAULT_ALLOWED_DOMAINS
        # BrowserTool lanzaria realmente, pero solo probamos que check pasa
        decision = bridge.check("https://api.github.com/repos/therealronin23/atlas")
        assert decision.allowed is True


class TestBrowserAudit:

    def test_blocked_navigation_is_logged(
        self,
        tmp_path: Path,
        merkle: MerkleLogger,
    ) -> None:
        bt = BrowserTool(workspace=tmp_path, headless=True, merkle=merkle)

        with pytest.raises(PermissionError):
            bt.navigate("http://evil.com/malware")

        records = merkle.tail(5)
        assert records[-1].action == "browser.navigate"
        assert records[-1].result == "blocked"
        assert records[-1].agent == "browser.tool"

    def test_browser_actions_are_logged(
        self,
        http_server: str,
        tmp_path: Path,
        bridge_with_localhost: SSRFBridge,
        merkle: MerkleLogger,
    ) -> None:
        bt = BrowserTool(
            workspace=tmp_path,
            bridge=bridge_with_localhost,
            headless=True,
            merkle=merkle,
            allow_private_network=True,
        )
        try:
            bt.navigate(http_server + "/form.html")
            bt.fill("#name", "Atlas User")
            bt.screenshot("audit")
            bt.extract()
        finally:
            bt.close()

        actions = [r.action for r in merkle.tail(10)]
        assert "browser.launch" in actions
        assert "browser.navigate" in actions
        assert "browser.fill" in actions
        assert "browser.screenshot" in actions
        assert "browser.extract" in actions
        assert "browser.close" in actions

    def test_extra_allowed_localhost_still_requires_private_network_flag(
        self,
        http_server: str,
        tmp_path: Path,
        bridge_with_localhost: SSRFBridge,
        merkle: MerkleLogger,
    ) -> None:
        bt = BrowserTool(
            workspace=tmp_path,
            bridge=bridge_with_localhost,
            headless=True,
            merkle=merkle,
        )

        with pytest.raises(PermissionError, match="allow_private_network"):
            bt.navigate(http_server + "/index.html")

        records = merkle.tail(5)
        assert records[-1].action == "browser.navigate"
        assert records[-1].result == "blocked"
