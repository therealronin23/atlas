"""T4.1 — Descubrimiento abierto de candidatos del ecosistema.

Reescrito 2026-08-06. La versión anterior recibía un `CrawlerTool` en el
constructor y **no lo usaba**: salía por `urllib.request.urlopen` directo,
saltándose el `SSRFBridge` que el resto del repo atraviesa (fan-in 20) justo
para no permitir egress arbitrario. Además tragaba cualquier excepción con un
`logger.error`, así que una fuente caída y una fuente sin resultados producían
exactamente la misma salida: lista vacía.

Invariantes de este módulo:

1. **Ninguna URL se pide sin que el `SSRFBridge` la haya aprobado antes.** El
   bridge es el único que decide; este módulo no reimplementa validación.
2. **Un fallo se declara.** `ScoutReport.failures` lleva `(url, motivo)`; un
   catálogo incompleto nunca se disfraza de catálogo vacío.
3. **Una fuente caída no cancela las demás.**
"""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from atlas.security.ssrf_bridge import SSRFBridge

logger = logging.getLogger(__name__)

Fetcher = Callable[..., str]

DEFAULT_SOURCES: tuple[str, ...] = (
    "https://api.github.com/search/repositories?q=mcp+server+language:python",
    "https://api.github.com/search/repositories?q=modelcontextprotocol",
)

# Cuántos resultados se toman por fuente. Acotado a propósito: descubrimiento
# es un radar, no una descarga del ecosistema entero.
MAX_PER_SOURCE = 5


@dataclass(frozen=True)
class Candidate:
    """Un candidato tal y como lo publicó su fuente. Sin juicio: el veredicto
    es cosa de `DissectionPipeline`."""

    name: str
    url: str
    description: str
    source: str
    stars: int
    archived: bool = False
    license: str | None = None
    pushed_at: str | None = None


@dataclass(frozen=True)
class ScoutReport:
    candidates: tuple[Candidate, ...] = ()
    # (url, motivo) — una fuente que no se pudo consultar, y por qué.
    failures: tuple[tuple[str, str], ...] = ()


def _default_fetch(url: str, *, timeout: float = 10.0) -> str:
    """Salida HTTP real. Sólo se invoca DESPUÉS de que el bridge apruebe."""
    request = urllib.request.Request(  # noqa: S310 — esquema validado por SSRFBridge
        url,
        headers={"User-Agent": "Atlas-Scout/1.0", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body: str = response.read().decode("utf-8", errors="replace")
    return body


class EcosystemScout:
    """Descubre candidatos en fuentes externas, con egress gobernado."""

    def __init__(
        self,
        bridge: SSRFBridge,
        *,
        fetch: Fetcher | None = None,
        sources: Sequence[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._bridge = bridge
        self._fetch = fetch or _default_fetch
        self._sources = tuple(sources) if sources is not None else DEFAULT_SOURCES
        self._timeout = timeout

    def discover(self) -> ScoutReport:
        candidates: list[Candidate] = []
        failures: list[tuple[str, str]] = []
        for url in self._sources:
            decision = self._bridge.check(url)
            if not decision.allowed:
                failures.append((url, f"bridge SSRF bloqueo la URL: {decision.reason}"))
                continue
            try:
                raw = self._fetch(url, timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 — una fuente rota no cancela el barrido
                failures.append((url, f"{type(exc).__name__}: {exc}"))
                continue
            try:
                payload = json.loads(raw)
                items = payload["items"]
            except (ValueError, KeyError, TypeError) as exc:
                # GitHub devuelve HTML al limitar por rate: eso NO es "sin
                # resultados", es una consulta que no se pudo hacer.
                failures.append(
                    (url, f"respuesta no interpretable: {type(exc).__name__}: {exc}")
                )
                continue
            candidates.extend(self._parse(items, source=self._source_label(url)))
        return ScoutReport(tuple(candidates), tuple(failures))

    @staticmethod
    def _source_label(url: str) -> str:
        """Etiqueta el CANAL, no la consulta: dos búsquedas distintas en GitHub
        no son dos fuentes independientes, y confundirlo rompería la
        corroboración cruzada de `EcosystemDigestion`."""
        return "github_search" if "api.github.com" in url else "http"

    @staticmethod
    def _parse(items: Any, *, source: str) -> list[Candidate]:
        out: list[Candidate] = []
        if not isinstance(items, list):
            return out
        for item in items[:MAX_PER_SOURCE]:
            if not isinstance(item, dict):
                continue
            license_block = item.get("license") or {}
            spdx = (
                license_block.get("spdx_id") if isinstance(license_block, dict) else None
            )
            out.append(
                Candidate(
                    name=str(item.get("name") or ""),
                    url=str(item.get("html_url") or ""),
                    description=str(item.get("description") or ""),
                    source=source,
                    stars=int(item.get("stargazers_count") or 0),
                    archived=bool(item.get("archived", False)),
                    license=str(spdx) if spdx else None,
                    pushed_at=item.get("pushed_at"),
                )
            )
        return out
