"""ADR-039 slice 5 — Scout community (foros) con corroboración obligatoria.

Los foros son el vector de inyección de mayor valor del sistema (§Riesgos del
ADR). Por eso este Scout aplica la regla de Tomás —"nada que no esté
contrastado"— de forma estructural, no como buena voluntad:

- **El foro solo aporta señal de descubrimiento, jamás autoridad.** De la prosa
  del foro se extrae únicamente un *nombre candidato*; ese nombre se contrasta
  contra la fuente autoritativa (registro MCP oficial) vía ``authoritative_lookup``.
- **Fail-closed:** si el nombre no existe en la fuente autoritativa, se descarta.
  Un candidato "solo-foro" **nunca** llega a proponerse.
- **Los campos de la propuesta salen del candidato autoritativo** (nombre,
  versión, cmd, tools), no de la prosa del foro. El excerpt del foro viaja como
  ``Source(community)`` no confiable: solo lo digiere el processing-LLM del
  Analyst (CaMeL), nunca fija un campo de decisión.
- **Egress gateado:** cada URL de foro pasa por ``SSRFBridge.check`` (foros
  controlados vía allowlist). Denegada → se omite.

El resultado es un ``McpCandidate`` que ya lleva la fuente autoritativa **y** la
community: el gate de corroboración del Analyst (sólo autoritativas corroboran)
pasa por el respaldo real, y queda traza de que el foro lo *surgió*.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from atlas.core.self_maintenance.candidate import (
    PROVENANCE_COMMUNITY,
    McpCandidate,
    Source,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

# Cota del excerpt no confiable que se transporta al Analyst.
_EXCERPT_MAX = 500

# Extractor por defecto: tokens con pinta de paquete MCP (``@scope/name``,
# ``mcp-foo``, ``foo-mcp``). No interpreta semántica: solo *surge* nombres que
# luego deben corroborarse contra la fuente autoritativa.
_DEFAULT_MENTION = re.compile(
    r"(@[\w.-]+/[\w.-]+|[\w.-]*mcp[\w.-]*)", re.IGNORECASE
)


def _default_extractor(body: str) -> list[str]:
    seen: list[str] = []
    for m in _DEFAULT_MENTION.finditer(body):
        tok = m.group(1).strip(".-/")
        if len(tok) >= 3 and tok not in seen:
            seen.append(tok)
    return seen


class CommunityScout:
    """Descubre candidatos en foros, pero solo propone lo corroborado (slice 5)."""

    AGENT = "self_maintenance.community_scout"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        bridge: SSRFBridge,
        fetch: Callable[[str], str],
        forum_urls: list[str],
        authoritative_lookup: Callable[[str], McpCandidate | None],
        extract_mentions: Callable[[str], list[str]] = _default_extractor,
    ) -> None:
        self._merkle = merkle
        self._bridge = bridge
        self._fetch = fetch
        self._forum_urls = forum_urls
        self._lookup = authoritative_lookup
        self._extract = extract_mentions

    def discover(self) -> list[McpCandidate]:
        """Candidatos de foro **corroborados** por fuente autoritativa. Fail-closed."""
        candidates: list[McpCandidate] = []
        seen: set[str] = set()
        surfaced = 0
        for url in self._forum_urls:
            if not self._bridge.check(url).allowed:
                continue
            try:
                body = self._fetch(url)
            except Exception:  # noqa: BLE001 — fail-closed: foro caído → se omite
                continue
            for name in self._extract(body):
                surfaced += 1
                auth = self._lookup(name)
                if auth is None or auth.name in seen:
                    continue  # sin respaldo autoritativo → nunca se propone
                seen.add(auth.name)
                excerpt = self._excerpt_for(body, name)
                candidates.append(McpCandidate(
                    name=auth.name,
                    version=auth.version,
                    cmd=list(auth.cmd),
                    declared_tools=list(auth.declared_tools),
                    # Autoritativa(s) primero (fijan los campos vía corroboración)
                    # + community (solo prosa no confiable, para traza/Analyst).
                    sources=[*auth.sources, Source(
                        provenance=PROVENANCE_COMMUNITY,
                        url=url,
                        raw_excerpt=excerpt,
                    )],
                ))
        self._audit(surfaced, [c.name for c in candidates])
        return candidates

    @staticmethod
    def _excerpt_for(body: str, name: str) -> str:
        """Extrae una ventana acotada alrededor de la mención (dato no confiable)."""
        idx = body.find(name)
        if idx < 0:
            return ""
        start = max(0, idx - _EXCERPT_MAX // 2)
        return body[start:start + _EXCERPT_MAX]

    def _audit(self, surfaced: int, corroborated: list[str]) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.community_scout_discover",
                agent=self.AGENT,
                result="ok",
                risk_level="safe",
                payload={
                    "surfaced": surfaced,
                    "corroborated_count": len(corroborated),
                    "corroborated": corroborated,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe el descubrimiento
            pass
