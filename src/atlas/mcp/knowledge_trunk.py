"""
Atlas Core — KnowledgeTrunk: la raíz `knowledge-src` del MCP trunk portable (F3).

Capa NEUTRA, transport-agnostic: expone APIs libres (Wikipedia para empezar) como
tools y cablea la ingesta al sustrato verificable vía `run_mission`. El bucle único
del design doc: knowledge-src → run_mission → memoria con PROCEDENCIA.

Honesto: "conocimiento verificable" = procedencia (fuente + fecha + hash), NO
prueba de verdad. El `KnowledgeVerifier` filtra grounding (provenance bien formada,
hash que casa, content no vacío); no juzga veracidad.

NO sabe nada de MCP; el shell FastMCP se monta encima. Fetcher inyectable → el
acceso a red lo decide el caller (tests sin red).

Diseño: docs/design/mcp_trunk_portable.md (F3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.knowledge.base import KnowledgeBase
from atlas.knowledge.mission import Mission
from atlas.knowledge.run import run_mission
from atlas.knowledge.sources import Fetcher, HttpApiSource, RawRecord
from atlas.knowledge.verifier import KnowledgeVerifier
from atlas.security.ssrf_bridge import SSRFBridge

_WIKI_DOMAIN = "knowledge/wikipedia"


class WikipediaSource(HttpApiSource):
    """Fuente Wikipedia (REST summary API). Añade su dominio al gate SSRF (no está
    en el allowlist por defecto) y pega a `/page/summary/<title>`."""

    def __init__(self, *, fetcher: Fetcher | None = None, lang: str = "en") -> None:
        host = f"{lang}.wikipedia.org"
        super().__init__(
            "wikipedia",
            _WIKI_DOMAIN,
            bridge=SSRFBridge(extra_allowed={host}),
            fetcher=fetcher,
        )
        self._host = host

    def fetch(self, query: Any) -> list[RawRecord]:
        title = str(query).strip().replace(" ", "_")
        url = f"https://{self._host}/api/rest_v1/page/summary/{title}"
        return [self._request("GET", url)]


class KnowledgeTrunk:
    """Tools de conocimiento libre + ingesta cableada al sustrato."""

    def __init__(self, base_root: Path, *, fetcher: Fetcher | None = None) -> None:
        self._base = KnowledgeBase(Path(base_root))
        self._verifier = KnowledgeVerifier()
        self._wiki = WikipediaSource(fetcher=fetcher)

    def wikipedia(self, title: str) -> list[dict[str, Any]]:
        """Lookup crudo (sin ingestar): payload + url + status, con procedencia
        de la URL. Útil para inspeccionar antes de comprometer al sustrato."""
        return [
            {"url": r.url, "status": r.status, "payload": r.payload}
            for r in self._wiki.fetch(title)
        ]

    def ingest_wikipedia(
        self, title: str, *, domain: str = _WIKI_DOMAIN, goal: str = ""
    ) -> dict[str, Any]:
        """Ejecuta run_mission con la fuente Wikipedia → verifica → sustrato.
        Devuelve conteos + ids ingeridos + errores por fuente."""
        mission = Mission(
            id=f"wiki:{title}",
            domain=domain,
            goal=goal,
            source_ids=["wikipedia"],
            cadence_s=0,
        )
        report = run_mission(
            mission,
            sources={"wikipedia": self._wiki},
            base=self._base,
            verifier=self._verifier,
            queries={"wikipedia": title},
        )
        return {
            "ingested": report.ingested,
            "rejected": report.rejected,
            "ingested_ids": list(report.ingested_ids),
            "errors": [list(e) for e in report.errors],
        }

    def query(self, domain: str = _WIKI_DOMAIN) -> list[dict[str, Any]]:
        """Lo que ya entró al sustrato para un dominio (con su procedencia)."""
        return [a.to_dict() for a in self._base.query(domain)]
