"""PanoramaScout -- descubrimiento por TEMA DE INTERES, no por lista de fuentes fijas.

El usuario corrigio al asistente: el ecosistema no es una lista de fuentes
conocidas (Hermes/Cursor/Odysseus) -- puede ser un paper, un lenguaje nuevo, un
SaaS que no tiene nombre todavia. "Descubri mempalace por un reel de
Instagram, no porque lo vigilara." Los scouts existentes de Atlas
(``RegistryScout``, ``CommunityScout``) descubren contra fuentes/URLs FIJAS --
exactamente la limitacion senalada.

``PanoramaScout`` es el primer escalon real hacia "serendipia sistematizada":
descubrir por TEMA DE INTERES (no por URL fija). Fuentes: GitHub (repos
search API, ``api.github.com``), Hacker News (Algolia search API,
``hn.algolia.com``) y arXiv (``export.arxiv.org``, Atom; anadido a la
allowlist con OK explicito del operador 2026-07-10 — era la decision de
ampliar superficie de red que este modulo dejaba fuera de alcance). Cada
fuente falla de forma INDEPENDIENTE: un tema roto en una fuente no bloquea
esa misma fuente para otros temas ni las demas fuentes de ese mismo tema.

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
from urllib.parse import quote_plus

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

# Endpoint de busqueda de repos de GitHub (ya en DEFAULT_ALLOWED_DOMAINS).
_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# Endpoint de busqueda de Hacker News via Algolia (ya en DEFAULT_ALLOWED_DOMAINS).
_HACKERNEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

# Endpoint de la API de arXiv (Atom XML; en DEFAULT_ALLOWED_DOMAINS desde
# 2026-07-10 con OK explicito del operador).
_ARXIV_SEARCH_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Cota del excerpt no confiable que se transporta (misma logica que los demas
# scouts: dato NO confiable, solo lo digiere el processing-LLM del Analyst).
_EXCERPT_MAX = 300


@dataclass
class PanoramaFinding:
    """Un hallazgo generico del ecosistema, originado por TEMA, no por URL."""

    topic: str  # el tema de interes que origino la busqueda (no una URL)
    source: str  # "github" | "hackernews" | "arxiv"
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
    algo sin nombre todavia. Fuentes: GitHub (repos search API), HN Algolia
    (search API) y arXiv (Atom API; allowlist ampliada con OK del operador
    2026-07-10); cada fuente falla de forma independiente por tema."""

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
            findings.extend(self._search_arxiv(topic))
        return findings

    def _search_github(self, topic: str) -> list[PanoramaFinding]:
        """Busca en GitHub repos ordenados por actualizacion reciente.
        Fail-closed: egress denegado o fetch/parseo roto -> [] (auditado),
        sin propagar la excepcion."""
        url = (
            f"{_GITHUB_SEARCH_URL}?q={quote_plus(topic)}"
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
            f"{_HACKERNEWS_SEARCH_URL}?query={quote_plus(topic)}"
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

    def _search_arxiv(self, topic: str) -> list[PanoramaFinding]:
        """Busca papers en arXiv (Atom XML, stdlib ElementTree). Ordena por
        fecha de envio descendente — lo NUEVO del tema, coherente con el
        sort=updated de GitHub. Fail-closed por fuente/tema como las demas."""
        url = (
            f"{_ARXIV_SEARCH_URL}?search_query=all:{quote_plus(topic)}"
            f"&sortBy=submittedDate&sortOrder=descending&max_results={self._max_results}"
        )
        decision = self._bridge.check(url)
        if not decision.allowed:
            self._audit(topic, "egress_denied", 0, reason=decision.reason, source="arxiv")
            return []
        try:
            import xml.etree.ElementTree as ET  # noqa: PLC0415 -- stdlib, solo esta fuente

            root = ET.fromstring(self._fetch(url))
            entries = root.findall(f"{_ATOM_NS}entry")
        except Exception as exc:  # noqa: BLE001 -- fail-closed por fuente
            self._audit(topic, "fetch_failed", 0, reason=type(exc).__name__, source="arxiv")
            return []
        topic_findings: list[PanoramaFinding] = []
        for entry in entries[: self._max_results]:
            title = (entry.findtext(f"{_ATOM_NS}title") or "").strip()
            link = (entry.findtext(f"{_ATOM_NS}id") or "").strip()
            summary = " ".join((entry.findtext(f"{_ATOM_NS}summary") or "").split())
            topic_findings.append(
                PanoramaFinding(
                    topic=topic,
                    source="arxiv",
                    title=title,
                    url=link,
                    excerpt=summary[:_EXCERPT_MAX],
                )
            )
        self._audit(topic, "discovered", len(topic_findings), source="arxiv")
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
