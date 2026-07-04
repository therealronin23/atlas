"""
Atlas Core — Crawler Tool (scraping absorbido de Crawl4AI, 2026-07-02).

Extrae markdown LLM-friendly de una URL pública. Misma disciplina de
gobernanza que ``BrowserTool``: pasa por SSRF Bridge antes de tocar la red,
bloquea red privada/local salvo opt-in explícito, y audita cada llamada en
Merkle. Es de SOLO LECTURA (nunca muta el host) pero su contenido es de una
fuente externa NO confiable — el loop agéntico debe envolverlo (ADR-037),
nunca tratarlo como instrucción.

Aislamiento de proceso (deliberado, no accidental): Crawl4AI corre en un venv
SEPARADO (``.venv-scraping``) porque fija ``unclecode-litellm==1.81.13``, un
fork que se instala bajo el mismo nombre de import que nuestro ``litellm``
real — instalarlo en el venv principal reemplazaría silenciosamente la
librería de la que depende ``InferenceHub``. Ver ``_crawl4ai_worker.py``.
"""

from __future__ import annotations

import ipaddress
import json
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PYTHON = _REPO_ROOT / ".venv-scraping" / "bin" / "python3"
_WORKER = Path(__file__).resolve().parent / "_crawl4ai_worker.py"
_MAX_MARKDOWN_CHARS = 20000


@dataclass(frozen=True)
class CrawlResult:
    url: str
    success: bool
    status_code: int | None
    markdown: str
    duration_ms: int
    error: str | None = None


class CrawlerTool:
    """Scraping gobernado vía Crawl4AI, aislado en su propio venv/proceso."""

    def __init__(
        self,
        workspace: Path,
        bridge: SSRFBridge | None = None,
        merkle: MerkleLogger | None = None,
        allow_private_network: bool = False,
        python_bin: Path | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._workspace = workspace
        self._bridge = bridge or SSRFBridge()
        self._merkle = merkle
        self._allow_private_network = allow_private_network
        self._python_bin = python_bin or _DEFAULT_PYTHON
        self._timeout_s = timeout_s

    @property
    def is_available(self) -> bool:
        """False si el venv aislado de Crawl4AI no está instalado."""
        return self._python_bin.is_file()

    def crawl(self, url: str, *, max_chars: int = _MAX_MARKDOWN_CHARS) -> CrawlResult:
        decision = self._bridge.check(url)
        if not decision.allowed:
            self._log("crawler.crawl", "blocked", risk_level="high",
                       payload={"url": url, "reason": decision.reason})
            raise PermissionError(f"SSRF Bridge bloqueo la URL: {decision.reason}")
        if self._is_private_or_local_url(url) and not self._allow_private_network:
            reason = "URL local/privada requiere allow_private_network=True"
            self._log("crawler.crawl", "blocked", risk_level="high",
                       payload={"url": url, "reason": reason})
            raise PermissionError(reason)
        if not self.is_available:
            reason = (
                f"venv aislado de Crawl4AI no encontrado en {self._python_bin}. "
                "Ejecuta: python3 -m venv .venv-scraping && "
                ".venv-scraping/bin/pip install crawl4ai && "
                ".venv-scraping/bin/python3 -m playwright install chromium"
            )
            self._log("crawler.crawl", "failed", risk_level="moderate",
                       payload={"url": url, "error": reason})
            return CrawlResult(url=url, success=False, status_code=None,
                                markdown="", duration_ms=0, error=reason)

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                [str(self._python_bin), str(_WORKER), url, str(max_chars)],
                capture_output=True, text=True, timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._log("crawler.crawl", "failed", risk_level="moderate",
                       payload={"url": url, "error": "timeout", "duration_ms": duration_ms})
            return CrawlResult(url=url, success=False, status_code=None,
                                markdown="", duration_ms=duration_ms, error="timeout")

        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            out = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
        except (json.JSONDecodeError, IndexError):
            out = {}
        if not isinstance(out, dict) or "success" not in out:
            error = f"worker no devolvió JSON válido: {(proc.stderr or proc.stdout)[:500]}"
            self._log("crawler.crawl", "failed", risk_level="moderate",
                       payload={"url": url, "error": error, "duration_ms": duration_ms})
            return CrawlResult(url=url, success=False, status_code=None,
                                markdown="", duration_ms=duration_ms, error=error)

        result = CrawlResult(
            url=url,
            success=bool(out.get("success")),
            status_code=out.get("status_code"),
            markdown=str(out.get("markdown") or ""),
            duration_ms=duration_ms,
            error=out.get("error") or None,
        )
        self._log(
            "crawler.crawl",
            "ok" if result.success else "failed",
            risk_level="safe" if result.success else "moderate",
            payload={
                "url": url, "status_code": result.status_code,
                "duration_ms": duration_ms, "markdown_chars": len(result.markdown),
                "error": result.error,
            },
        )
        return result

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
        self, action: str, result: str, *,
        risk_level: str = "safe", payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action, agent="crawler.tool", result=result,
            risk_level=risk_level, payload=payload or {},
        )
