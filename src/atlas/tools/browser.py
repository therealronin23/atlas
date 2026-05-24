"""
Atlas Core — Browser Tool (Gate F/F1)
Computer-use via Playwright + Chromium headless.

Herramientas:
  - browser.navigate: navegar a URL y extraer texto.
  - browser.screenshot: capturar screenshot de pagina.
  - browser.fill: rellenar campo de formulario.
  - browser.click: hacer click en un elemento.
  - browser.extract: extraer texto sin navegar (desde URL ya abierta).

Todas pasan por SSRF Bridge antes de abrir conexion. El contexto del
navegador es persistente durante la sesion (Playwright BrowserContext
en ~/atlas/tmp/browser_data/).
"""

from __future__ import annotations

import ipaddress
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge


# ---------------------------------------------------------------------------
# Resultados tipados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NavigationResult:
    url: str
    title: str
    text: str
    status_code: int
    duration_ms: int


@dataclass(frozen=True)
class ScreenshotResult:
    path: str
    width: int
    height: int
    bytes_size: int


@dataclass(frozen=True)
class FillResult:
    success: bool
    selector: str
    value: str
    error: str | None = None


@dataclass(frozen=True)
class ClickResult:
    success: bool
    selector: str
    error: str | None = None


@dataclass(frozen=True)
class ExtractResult:
    text: str
    url: str
    title: str


# ---------------------------------------------------------------------------
# Browser tool
# ---------------------------------------------------------------------------


class BrowserTool:
    """
    Navegador headless via Playwright + Chromium.
    Abre un contexto persistente en el workspace.

    Uso tipico:

        bt = BrowserTool(workspace=Path("~/atlas"), bridge=SSRFBridge())
        nav = bt.navigate("https://example.com")
        print(nav.text[:200])
        ss = bt.screenshot("page")
        bt.fill("#search", "Atlas Core")
        bt.click("#search-button")
        bt.close()
    """

    SCREENSHOT_DIR = "tmp/screenshots"

    def __init__(
        self,
        workspace: Path,
        bridge: SSRFBridge | None = None,
        headless: bool = True,
        merkle: MerkleLogger | None = None,
        allow_private_network: bool = False,
    ) -> None:
        self._workspace = workspace
        self._bridge = bridge or SSRFBridge()
        self._headless = headless
        self._merkle = merkle
        self._allow_private_network = allow_private_network
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._screenshot_dir = workspace / self.SCREENSHOT_DIR
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._launched = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def launch(self) -> None:
        """Arranca Playwright + Chromium + contexto persistente."""
        if self._launched:
            return
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            raise RuntimeError(
                "Playwright no instalado. Ejecuta: pip install playwright && "
                "python -m playwright install chromium"
            ) from None

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AtlasCore/0.4",
            storage_state=None,
        )
        self._page = self._context.new_page()
        self._launched = True
        self._log(
            "browser.launch",
            "ok",
            payload={"headless": self._headless, "workspace": str(self._workspace)},
        )

    def close(self) -> None:
        """Cierra el navegador y libera recursos."""
        try:
            if self._page is not None:
                self._page.close()
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:  # pragma: no cover
            pass
        finally:
            self._launched = False
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._log("browser.close", "ok", payload={})

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def navigate(self, url: str, *, timeout_ms: int = 30000) -> NavigationResult:
        """Navega a una URL validada por SSRF Bridge y extrae texto."""
        decision = self._bridge.check(url)
        if not decision.allowed:
            self._log(
                "browser.navigate",
                "blocked",
                risk_level="high",
                payload={"url": url, "reason": decision.reason},
            )
            raise PermissionError(
                f"SSRF Bridge bloqueo la URL: {decision.reason}"
            )
        if self._is_private_or_local_url(url) and not self._allow_private_network:
            reason = "URL local/privada requiere allow_private_network=True"
            self._log(
                "browser.navigate",
                "blocked",
                risk_level="high",
                payload={"url": url, "reason": reason},
            )
            raise PermissionError(reason)

        if not self._launched:
            self.launch()

        start = time.perf_counter()
        assert self._page is not None
        try:
            response = self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else 0
            # Esperar un poco para que cargue el contenido dinamico
            self._page.wait_for_timeout(500)
            title = self._page.title()
            text = self._page.inner_text("body") or ""
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._log(
                "browser.navigate",
                "ok",
                payload={
                    "url": url,
                    "status_code": status,
                    "duration_ms": duration_ms,
                    "text_chars": min(len(text), 10000),
                },
            )
            return NavigationResult(
                url=url,
                title=title,
                text=text[:10000],  # limitar a 10k chars
                status_code=status,
                duration_ms=duration_ms,
            )
        except Exception as e:
            self._log(
                "browser.navigate",
                "failed",
                risk_level="moderate",
                payload={"url": url, "error": str(e)[:500]},
            )
            raise

    def screenshot(self, name: str | None = None) -> ScreenshotResult:
        """Captura screenshot de la pagina actual."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado. Llama a navigate() primero.")

        assert self._page is not None
        ts = int(time.time())
        fname = name or f"screenshot_{ts}"
        path = self._screenshot_dir / f"{fname}.png"

        self._page.screenshot(path=str(path), full_page=True)
        size = path.stat().st_size
        viewport = self._page.viewport_size or {"width": 1280, "height": 720}
        self._log(
            "browser.screenshot",
            "ok",
            payload={
                "path": str(path),
                "bytes_size": size,
                "width": viewport.get("width", 1280),
                "height": viewport.get("height", 720),
            },
        )

        return ScreenshotResult(
            path=str(path),
            width=viewport.get("width", 1280),
            height=viewport.get("height", 720),
            bytes_size=size,
        )

    def fill(self, selector: str, value: str) -> FillResult:
        """Rellena un campo de formulario."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado.")

        assert self._page is not None
        try:
            self._page.fill(selector, value)
            self._log(
                "browser.fill",
                "ok",
                payload={"selector": selector, "value_length": len(value)},
            )
            return FillResult(success=True, selector=selector, value=value)
        except Exception as e:
            self._log(
                "browser.fill",
                "failed",
                risk_level="moderate",
                payload={"selector": selector, "error": str(e)[:500]},
            )
            return FillResult(success=False, selector=selector, value=value, error=str(e))

    def click(self, selector: str) -> ClickResult:
        """Hace click en un elemento."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado.")

        assert self._page is not None
        try:
            self._page.click(selector, timeout=5000)
            self._log("browser.click", "ok", payload={"selector": selector})
            return ClickResult(success=True, selector=selector)
        except Exception as e:
            self._log(
                "browser.click",
                "failed",
                risk_level="moderate",
                payload={"selector": selector, "error": str(e)[:500]},
            )
            return ClickResult(success=False, selector=selector, error=str(e))

    def extract(self) -> ExtractResult:
        """Extrae texto y titulo de la pagina actual."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado.")

        assert self._page is not None
        text = self._page.inner_text("body") or ""
        title = self._page.title()
        url = self._page.url
        self._log(
            "browser.extract",
            "ok",
            payload={"url": url, "title": title, "text_chars": min(len(text), 10000)},
        )

        return ExtractResult(text=text[:10000], url=url, title=title)

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------

    @property
    def is_launched(self) -> bool:
        return self._launched

    @property
    def current_url(self) -> str:
        if self._page is not None:
            return self._page.url
        return ""

    @property
    def screenshot_dir(self) -> Path:
        return self._screenshot_dir

    def _is_private_or_local_url(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "0.0.0.0"}:
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip.is_link_local

    def _log(
        self,
        action: str,
        result: str,
        *,
        risk_level: str = "safe",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action,
            agent="browser.tool",
            result=result,
            risk_level=risk_level,
            payload=payload or {},
        )
