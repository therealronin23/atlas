"""PanoramaScout -- descubrimiento por TEMA DE INTERES, no por lista de fuentes fijas.

El usuario corrigio al asistente: el ecosistema no es una lista de fuentes
conocidas (Hermes/Cursor/Odysseus) -- puede ser un paper, un lenguaje nuevo, un
SaaS que no tiene nombre todavia. "Descubri mempalace por un reel de
Instagram, no porque lo vigilara." Los scouts existentes de Atlas
(``RegistryScout``, ``CommunityScout``) descubren contra fuentes/URLs FIJAS --
exactamente la limitacion senalada.

``PanoramaScout`` es el primer escalon real hacia "serendipia sistematizada":
descubrir por TEMA DE INTERES (no por URL fija). Alcance HONESTO de este
slice: SOLO GitHub (repos search API, ``api.github.com``, ya en
``DEFAULT_ALLOWED_DOMAINS`` de ``SSRFBridge`` -- no hace falta ampliar la
allowlist). HN Algolia (``hn.algolia.com``) y arXiv (``arxiv.org``) son
fuentes naturales a anadir despues con el MISMO patron -- fuera de alcance
aqui, para no mezclar 3 integraciones de API distintas en una sola pieza.

A diferencia de ``McpCandidate`` (tipado especificamente para servers MCP),
un hallazgo de PanoramaScout es generico: puede ser cualquier cosa del
ecosistema. Por eso usa su propio dataclass, ``PanoramaFinding``, en vez de
reutilizar ``McpCandidate``.

No posee la red: recibe ``fetch`` y ``bridge`` por inyeccion. Los tests pasan
un ``fetch`` falso -> CERO red real en la suite (regla del proyecto).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

# Endpoint de busqueda de repos de GitHub (ya en DEFAULT_ALLOWED_DOMAINS).
_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# Cota del excerpt no confiable que se transporta (misma logica que los demas
# scouts: dato NO confiable, solo lo digiere el processing-LLM del Analyst).
_EXCERPT_MAX = 300


@dataclass
class PanoramaFinding:
    """Un hallazgo generico del ecosistema, originado por TEMA, no por URL."""

    topic: str  # el tema de interes que origino la busqueda (no una URL)
    source: str  # "github" en este slice; "hackernews"/"arxiv" quedan para despues
    title: str
    url: str
    excerpt: str
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "excerpt": self.excerpt,
            "discovered_at": self.discovered_at,
        }


class PanoramaScout:
    """Descubre por TEMA DE INTERES, no por lista de fuentes fijas -- el hueco
    que el usuario senalo: el ecosistema no es una lista conocida, puede ser
    algo sin nombre todavia. Este slice usa SOLO GitHub (repos search API,
    ya en la allowlist); HN Algolia y arXiv son fuentes naturales a anadir
    despues con el mismo patron (fuera de alcance aqui, no fingir mas)."""

    AGENT = "self_maintenance.panorama_scout"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        bridge: SSRFBridge,
        fetch: Callable[[str], str],
        topics: list[str],
        max_results_per_topic: int = 5,
    ) -> None:
        self._merkle = merkle
        self._bridge = bridge
        self._fetch = fetch
        self._topics = topics
        self._max_results = max_results_per_topic

    def discover(self) -> list[PanoramaFinding]:
        """Por cada tema en self._topics, busca en GitHub repos ordenados por
        actualizacion reciente. Fail-closed por tema: si el egress se
        deniega o el fetch/parseo falla para UN tema, se salta ese tema
        (se audita) y se sigue con los demas -- un tema roto no debe tumbar
        el descubrimiento completo."""
        findings: list[PanoramaFinding] = []
        for topic in self._topics:
            url = (
                f"{_GITHUB_SEARCH_URL}?q={topic.replace(' ', '+')}"
                f"&sort=updated&order=desc&per_page={self._max_results}"
            )
            decision = self._bridge.check(url)
            if not decision.allowed:
                self._audit(topic, "egress_denied", 0, reason=decision.reason)
                continue
            try:
                body = self._fetch(url)
                data = json.loads(body)
                items = data.get("items", []) if isinstance(data, dict) else []
            except Exception as exc:  # noqa: BLE001 -- fail-closed por tema
                self._audit(topic, "fetch_failed", 0, reason=type(exc).__name__)
                continue
            topic_findings = [
                PanoramaFinding(
                    topic=topic,
                    source="github",
                    title=item.get("full_name", ""),
                    url=item.get("html_url", ""),
                    excerpt=(item.get("description") or "")[:_EXCERPT_MAX],
                )
                for item in items[: self._max_results]
                if isinstance(item, dict)
            ]
            findings.extend(topic_findings)
            self._audit(topic, "discovered", len(topic_findings))
        return findings

    def _audit(self, topic: str, result: str, count: int, *, reason: str = "") -> None:
        try:
            self._merkle.log(
                action="self_maintenance.panorama_scout_discover",
                agent=self.AGENT,
                result=result,
                risk_level="safe",
                payload={"topic": topic, "count": count, "reason": reason},
            )
        except Exception:  # noqa: BLE001 -- la auditoria no rompe el descubrimiento
            pass
