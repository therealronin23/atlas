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

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    ) -> None:
        self._workspace = workspace
        self._bridge = bridge or SSRFBridge()
        self._headless = headless
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
        data_dir = str(self._workspace / "tmp" / "browser_data")
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

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def navigate(self, url: str, *, timeout_ms: int = 30000) -> NavigationResult:
        """Navega a una URL validada por SSRF Bridge y extrae texto."""
        decision = self._bridge.check(url)
        if not decision.allowed:
            raise PermissionError(
                f"SSRF Bridge bloqueo la URL: {decision.reason}"
            )

        if not self._launched:
            self.launch()

        start = time.perf_counter()
        assert self._page is not None
        response = self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        status = response.status if response else 0
        # Esperar un poco para que cargue el contenido dinamico
        self._page.wait_for_timeout(500)
        title = self._page.title()
        text = self._page.inner_text("body") or ""
        duration_ms = int((time.perf_counter() - start) * 1000)

        return NavigationResult(
            url=url,
            title=title,
            text=text[:10000],  # limitar a 10k chars
            status_code=status,
            duration_ms=duration_ms,
        )

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
            return FillResult(success=True, selector=selector, value=value)
        except Exception as e:
            return FillResult(success=False, selector=selector, value=value, error=str(e))

    def click(self, selector: str) -> ClickResult:
        """Hace click en un elemento."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado.")

        assert self._page is not None
        try:
            self._page.click(selector, timeout=5000)
            return ClickResult(success=True, selector=selector)
        except Exception as e:
            return ClickResult(success=False, selector=selector, error=str(e))

    def extract(self) -> ExtractResult:
        """Extrae texto y titulo de la pagina actual."""
        if not self._launched:
            raise RuntimeError("Browser no lanzado.")

        assert self._page is not None
        text = self._page.inner_text("body") or ""
        title = self._page.title()
        url = self._page.url

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