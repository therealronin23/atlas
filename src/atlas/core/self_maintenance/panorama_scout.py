"""PanoramaScout -- descubrimiento por TEMA DE INTERES, no por lista de fuentes fijas.

El usuario corrigio al asistente: el ecosistema no es una lista de fuentes
conocidas (Hermes/Cursor/Odysseus) -- puede ser un paper, un lenguaje nuevo, un
SaaS que no tiene nombre todavia. "Descubri mempalace por un reel de
Instagram, no porque lo vigilara." Los scouts existentes de Atlas
(``RegistryScout``, ``CommunityScout``) descubren contra fuentes/URLs FIJAS --
exactamente la limitacion senalada.

``PanoramaScout`` es el primer escalon real hacia "serendipia sistematizada":
descubrir por TEMA DE INTERES (no por URL fija). Alcance de este slice:
GitHub (repos search API, ``api.github.com``) + Hacker News (Algolia search
API, ``hn.algolia.com``) -- ambos ya en ``DEFAULT_ALLOWED_DOMAINS`` de
``SSRFBridge``, no hace falta ampliar la allowlist. Cada fuente falla de
forma INDEPENDIENTE: un tema roto en una fuente no bloquea esa misma fuente
para otros temas ni las demas fuentes de ese mismo tema. arXiv
(``export.arxiv.org``) queda fuera de alcance: su API vive en un dominio que
HOY NO esta en la allowlist -- anadirlo implica una decision explicita de
ampliar la superficie de red, no una tarea de codigo, y no se hace aqui.

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

# Endpoint de busqueda de Hacker News via Algolia (ya en DEFAULT_ALLOWED_DOMAINS).
_HACKERNEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

# Cota del excerpt no confiable que se transporta (misma logica que los demas
# scouts: dato NO confiable, solo lo digiere el processing-LLM del Analyst).
_EXCERPT_MAX = 300


@dataclass
class PanoramaFinding:
    """Un hallazgo generico del ecosistema, originado por TEMA, no por URL."""

    topic: str  # el tema de interes que origino la busqueda (no una URL)
    source: str  # "github" o "hackernews" en este slice; "arxiv" queda para despues
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
    algo sin nombre todavia. Este slice usa GitHub (repos search API) + HN
    Algolia (search API), ambas ya en la allowlist; cada fuente falla de
    forma independiente por tema. arXiv queda fuera de alcance: su API
    (``export.arxiv.org``) no esta en la allowlist hoy -- ampliarla requiere
    decision explicita del usuario, no una tarea de codigo."""

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
        """Por cada tema en self._topics, busca en GitHub y en Hacker News.
        Fail-closed POR FUENTE y por tema: si una fuente falla (egress
        denegado o fetch/parseo roto) para un tema, esa fuente devuelve []
        para ese tema (se audita) pero la OTRA fuente sigue funcionando
        para el mismo tema, y los demas temas no se ven afectados."""
        findings: list[PanoramaFinding] = []
        for topic in self._topics:
            findings.extend(self._search_github(topic))
            findings.extend(self._search_hackernews(topic))
        return findings

    def _search_github(self, topic: str) -> list[PanoramaFinding]:
        """Busca en GitHub repos ordenados por actualizacion reciente.
        Fail-closed: egress denegado o fetch/parseo roto -> [] (auditado),
        sin propagar la excepcion."""
        url = (
            f"{_GITHUB_SEARCH_URL}?q={topic.replace(' ', '+')}"
            f"&sort=updated&order=desc&per_page={self._max_results}"
        )
        decision = self._bridge.check(url)
        if not decision.allowed:
            self._audit(topic, "egress_denied", 0, reason=decision.reason, source="github")
            return []
        try:
            body = self._fetch(url)
            data = json.loads(body)
            items = data.get("items", []) if isinstance(data, dict) else []
        except Exception as exc:  # noqa: BLE001 -- fail-closed por fuente
            self._audit(topic, "fetch_failed", 0, reason=type(exc).__name__, source="github")
            return []
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
        self._audit(topic, "discovered", len(topic_findings), source="github")
        return topic_findings

    def _search_hackernews(self, topic: str) -> list[PanoramaFinding]:
        """Busca historias en Hacker News via la API de Algolia. Si el hit
        no trae ``url`` (post de texto puro), cae al link del propio hilo
        de HN. Fail-closed: egress denegado o fetch/parseo roto -> [] para
        esta fuente en este tema (auditado), sin romper GitHub ni otros
        temas."""
        url = (
            f"{_HACKERNEWS_SEARCH_URL}?query={topic.replace(' ', '+')}"
            f"&tags=story&hitsPerPage={self._max_results}"
        )
        decision = self._bridge.check(url)
        if not decision.allowed:
            self._audit(topic, "egress_denied", 0, reason=decision.reason, source="hackernews")
            return []
        try:
            body = self._fetch(url)
            data = json.loads(body)
            hits = data.get("hits", []) if isinstance(data, dict) else []
        except Exception as exc:  # noqa: BLE001 -- fail-closed por fuente
            self._audit(topic, "fetch_failed", 0, reason=type(exc).__name__, source="hackernews")
            return []
        topic_findings = [
            PanoramaFinding(
                topic=topic,
                source="hackernews",
                title=hit.get("title", ""),
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                excerpt=(hit.get("story_text") or "")[:_EXCERPT_MAX],
            )
            for hit in hits[: self._max_results]
            if isinstance(hit, dict)
        ]
        self._audit(topic, "discovered", len(topic_findings), source="hackernews")
        return topic_findings

    def _audit(
        self, topic: str, result: str, count: int, *, reason: str = "", source: str = ""
    ) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.panorama_scout_discover",
                agent=self.AGENT,
                result=result,
                risk_level="safe",
                payload={"topic": topic, "count": count, "reason": reason, "source": source},
            )
        except Exception:  # noqa: BLE001 -- la auditoria no rompe el descubrimiento
            pass
