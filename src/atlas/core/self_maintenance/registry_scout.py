"""ADR-039 slice 1 (literal) — Scout externo autoritativo (read-only).

Descubre candidatos de server MCP en el **registro MCP oficial**
(``registry.modelcontextprotocol.io``), la fuente *autoritativa* del gate de
corroboración (ADR-039 §Gate de corroboración). A diferencia del Scout interno
(``scout.py``, salud/deuda), éste sí ingiere contenido **externo**, por lo que:

- **Egress gateado:** cada URL pasa por ``SSRFBridge.check`` antes de tocar la
  red. Denegada → se descarta y se audita; nunca se hace la request (fail-closed).
- **Contenido no confiable:** la prosa libre de cada entrada (descripción) viaja
  como ``Source.raw_excerpt`` — dato NO confiable que **solo** el processing-LLM
  del Analyst digiere tras ``wrap_untrusted`` (CaMeL, ADR-037). El Scout no razona
  sobre ella: solo la transporta etiquetada por procedencia.
- **Fail-closed en parseo:** JSON malformado o entradas corruptas → se omiten;
  nunca propagan una excepción ni fabrican un candidato a medias.

El Scout **no muta ni propone**: emite ``McpCandidate`` con ``provenance`` =
``authoritative``. Analyst (corroboración + dual-LLM) y Adopter vienen después.

No posee la red: recibe ``fetch`` y ``bridge`` por inyección. Los tests pasan un
``fetch`` falso → CERO red real en la suite (regla del proyecto).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from atlas.core.self_maintenance.candidate import (
    PROVENANCE_AUTHORITATIVE,
    McpCandidate,
    Source,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

# Endpoint del registro MCP oficial (lista de servers publicados).
REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"

# Cota de excerpt no confiable que se transporta al Analyst (anti-bloat / anti
# instrucción-camuflada; el Analyst lo acota de nuevo, defensa en profundidad).
_EXCERPT_MAX = 2000


class RegistryScout:
    """Descubre candidatos MCP en el registro oficial (ADR-039, autoritativo).

    ``discover()`` gatea el egress, descarga la lista, parsea entradas tolerante
    a fallos y devuelve ``McpCandidate`` etiquetados como autoritativos. Read-only.
    """

    AGENT = "self_maintenance.registry_scout"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        bridge: SSRFBridge,
        fetch: Callable[[str], str],
        registry_url: str = REGISTRY_URL,
    ) -> None:
        self._merkle = merkle
        self._bridge = bridge
        self._fetch = fetch
        self._registry_url = registry_url

    def discover(self) -> list[McpCandidate]:
        """Descubre candidatos autoritativos. Fail-closed en egress y parseo."""
        decision = self._bridge.check(self._registry_url)
        if not decision.allowed:
            self._audit("egress_denied", 0, reason=decision.reason)
            return []

        try:
            body = self._fetch(self._registry_url)
            entries = self._extract_entries(json.loads(body))
        except Exception as exc:  # noqa: BLE001 — fail-closed: red/JSON caídos → vacío
            self._audit("fetch_failed", 0, reason=type(exc).__name__)
            return []

        candidates: list[McpCandidate] = []
        for entry in entries:
            cand = self._parse_entry(entry)
            if cand is not None:
                candidates.append(cand)

        self._audit("ok", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Parseo tolerante (fail-closed por entrada)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_entries(data: Any) -> list[dict[str, Any]]:
        """Saca la lista de servers de la respuesta, tolerante a la forma exacta."""
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = data.get("servers") or data.get("data") or []
        else:
            raw = []
        entries: list[dict[str, Any]] = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            # Registro oficial (schema 2025-12-11): cada item envuelve el server
            # en {"server": {...}, "_meta": {...}}. Se desenvuelve si está.
            inner = e.get("server")
            entries.append(inner if isinstance(inner, dict) else e)
        return entries

    def _parse_entry(self, entry: dict[str, Any]) -> McpCandidate | None:
        """Convierte una entrada del registro en candidato. ``None`` si inservible."""
        try:
            name = str(entry.get("name") or "").strip()
            if not name:
                return None
            version = self._extract_version(entry)
            cmd = self._extract_cmd(entry, name)
            if not cmd:
                return None
            tools = self._extract_tools(entry)
            excerpt = str(entry.get("description") or "")[:_EXCERPT_MAX]
            source = Source(
                provenance=PROVENANCE_AUTHORITATIVE,
                url=self._registry_url,
                raw_excerpt=excerpt,
            )
            return McpCandidate(
                name=name,
                version=version,
                cmd=cmd,
                declared_tools=tools,
                sources=[source],
            )
        except Exception:  # noqa: BLE001 — una entrada corrupta no tumba la pasada
            return None

    @staticmethod
    def _extract_version(entry: dict[str, Any]) -> str:
        detail = entry.get("version_detail")
        if isinstance(detail, dict) and detail.get("version"):
            return str(detail["version"]).strip()
        if entry.get("version"):
            return str(entry["version"]).strip()
        return "0.0.0"

    @staticmethod
    def _extract_cmd(entry: dict[str, Any], name: str) -> list[str]:
        """Deriva el cmd de lanzamiento del primer package conocido.

        npm → ``npx -y <pkg>``; pypi → ``uvx <pkg>``. Sin package conocido no se
        propone cmd (devuelve ``[]`` → la entrada se descarta)."""
        packages = entry.get("packages")
        if not isinstance(packages, list):
            return []
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            registry = str(
                pkg.get("registry_name")
                or pkg.get("registry")
                or pkg.get("registryType")  # schema 2025-12-11 del registro oficial
                or ""
            ).lower()
            pkg_name = str(pkg.get("name") or pkg.get("identifier") or "").strip()
            if not pkg_name:
                continue
            if registry in ("npm", "npmjs"):
                return ["npx", "-y", pkg_name]
            if registry in ("pypi", "pip"):
                return ["uvx", pkg_name]
        return []

    @staticmethod
    def _extract_tools(entry: dict[str, Any]) -> list[str]:
        tools = entry.get("tools")
        out: list[str] = []
        if isinstance(tools, list):
            for t in tools:
                if isinstance(t, dict) and t.get("name"):
                    out.append(str(t["name"]).strip())
                elif isinstance(t, str):
                    out.append(t.strip())
        return out

    # ------------------------------------------------------------------

    def _audit(self, result: str, count: int, *, reason: str = "") -> None:
        try:
            self._merkle.log(
                action="self_maintenance.registry_scout_discover",
                agent=self.AGENT,
                result=result,
                risk_level="safe",
                payload={
                    "registry_url": self._registry_url,
                    "candidate_count": count,
                    "reason": reason,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe el descubrimiento
            pass
