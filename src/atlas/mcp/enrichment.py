"""
Atlas Core — Enriquecimiento del catálogo (Pieza 1).

Convierte entradas de catálogo que son solo nombres en entradas con
descripción-afirmada (`purpose_claimed`) y señal de popularidad (`signal`),
tirando metadatos de la fuente de cada entrada.

Principio wire-before-claim:
  - `purpose` solo se rellena si estaba vacío (nunca se sobreescribe).
  - `purpose_claimed=True` marca que viene de la fuente sin verificar.
  - `status` NUNCA se toca (eje ortogonal).
  - `signal` = prior de popularidad, no estado.

Diseño: docs/design/design_catalog_enrichment.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from atlas.knowledge.sources import Fetcher, HttpApiSource
from atlas.security.ssrf_bridge import SSRFBridge

_GH_HOST = "api.github.com"
_NPM_REGISTRY_HOST = "registry.npmjs.org"
_NPM_API_HOST = "api.npmjs.org"


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Enrichment:
    """Resultado de enriquecer una entrada con metadatos de su fuente.

    purpose_claimed: descripción afirmada (sin verificar) de la fuente.
    signal: popularidad / tracción. Claves según la fuente (stars, downloads…).
    """

    purpose_claimed: str
    signal: dict[str, int | float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol para inyección
# ---------------------------------------------------------------------------


class EnrichmentFetcher(Protocol):
    """Contrato para cualquier fetcher de enriquecimiento.

    fetch devuelve None cuando la fuente no da metadatos para esa entrada
    (404, caída, rate-limit, descripción vacía). wire-before-claim.
    """

    def fetch(self, source: str, name: str) -> Enrichment | None: ...


# ---------------------------------------------------------------------------
# GithubEnrichment — repo GitHub → description + stargazers_count
# ---------------------------------------------------------------------------


class GithubEnrichment(HttpApiSource):
    """Fetcher que obtiene metadatos de un repo GitHub.

    - source: '<owner>/<repo>' (el campo `source` de la entrada).
    - name: nombre del item (no usado aquí; el repo es la clave).
    - Fetcher HTTP INYECTABLE (igual que line_seed.py) → sin red en tests.
    - `api.github.com` allowlisted vía SSRFBridge.

    Devuelve None cuando:
      - HTTP != 200
      - description nula o vacía
    """

    def __init__(self, *, fetcher: Fetcher | None = None) -> None:
        super().__init__(
            "gh:enrichment",
            "enrichment/github",
            bridge=SSRFBridge(extra_allowed={_GH_HOST}),
            fetcher=fetcher,
        )

    def fetch(self, source: str, name: str) -> Enrichment | None:  # type: ignore[override]
        """source = 'owner/repo' tal como está en el YAML de catálogo."""
        url = f"https://{_GH_HOST}/repos/{source}"
        record = self._request("GET", url)
        if record.status != 200:
            return None
        try:
            data: dict[str, Any] = json.loads(record.payload)
        except (json.JSONDecodeError, ValueError):
            return None
        description: str = data.get("description") or ""
        if not description.strip():
            return None
        stars = data.get("stargazers_count")
        signal: dict[str, int | float] = {}
        if isinstance(stars, (int, float)):
            signal["stars"] = stars
        return Enrichment(purpose_claimed=description, signal=signal)


# ---------------------------------------------------------------------------
# NpmEnrichment — paquete npm → description + downloads
# ---------------------------------------------------------------------------


class NpmEnrichment(HttpApiSource):
    """Fetcher que obtiene metadatos de un paquete npm.

    - source: ignorado (el nombre del paquete viaja en `name`).
    - name: nombre del paquete npm.
    - Fetcher HTTP INYECTABLE → sin red en tests.
    - `registry.npmjs.org` + `api.npmjs.org` allowlisted vía SSRFBridge.

    Devuelve None cuando:
      - HTTP != 200
      - description nula o vacía

    Nota de diseño: el fetcher inyectable es el mismo para ambas llamadas
    (registry + downloads). En tests el fake devuelve el mismo payload para
    cualquier URL; en producción, el `_urllib_fetcher` hace las peticiones reales.
    """

    def __init__(self, *, fetcher: Fetcher | None = None) -> None:
        super().__init__(
            "npm:enrichment",
            "enrichment/npm",
            bridge=SSRFBridge(extra_allowed={_NPM_REGISTRY_HOST, _NPM_API_HOST}),
            fetcher=fetcher,
        )

    def fetch(self, source: str, name: str) -> Enrichment | None:  # type: ignore[override]
        """name = nombre del paquete npm."""
        pkg_url = f"https://{_NPM_REGISTRY_HOST}/{name}"
        record = self._request("GET", pkg_url)
        if record.status != 200:
            return None
        try:
            data: dict[str, Any] = json.loads(record.payload)
        except (json.JSONDecodeError, ValueError):
            return None
        description: str = data.get("description") or ""
        if not description.strip():
            return None

        # Intentar obtener downloads; si falla se incluye sin ese campo.
        signal: dict[str, int | float] = {}
        downloads = data.get("downloads")
        if isinstance(downloads, (int, float)):
            signal["downloads"] = downloads
        else:
            # Segundo endpoint: api.npmjs.org/downloads/point/last-month/<pkg>
            dl_url = f"https://{_NPM_API_HOST}/downloads/point/last-month/{name}"
            dl_record = self._request("GET", dl_url)
            if dl_record.status == 200:
                try:
                    dl_data: dict[str, Any] = json.loads(dl_record.payload)
                    dl_count = dl_data.get("downloads")
                    if isinstance(dl_count, (int, float)):
                        signal["downloads"] = dl_count
                except (json.JSONDecodeError, ValueError):
                    pass

        return Enrichment(purpose_claimed=description, signal=signal)


# ---------------------------------------------------------------------------
# enrich_entry — mezcla idempotente
# ---------------------------------------------------------------------------


def enrich_entry(entry: dict[str, Any], fetcher: EnrichmentFetcher) -> dict[str, Any]:
    """Enriquece una entrada del catálogo con metadatos de su fuente.

    Invariantes (nunca se violan):
    - `status` NUNCA se modifica.
    - `purpose` solo se rellena si estaba vacío (wire-before-claim).
    - Idempotente: llamar dos veces = mismo resultado.

    Devuelve una COPIA de la entrada con los campos añadidos/actualizados;
    no muta el dict original.

    Si fetcher.fetch devuelve None → entrada sin cambios (no se inventa nada).
    """
    result = dict(entry)  # copia superficial; no mutamos el original

    source: str = str(entry.get("source") or "")
    name: str = str(entry.get("name") or "")

    enrichment = fetcher.fetch(source, name)
    if enrichment is None:
        return result

    # purpose: solo si estaba vacío
    existing_purpose: str = str(entry.get("purpose") or "")
    if not existing_purpose.strip():
        result["purpose"] = enrichment.purpose_claimed
        result["purpose_claimed"] = True

    # signal: siempre se escribe (puede actualizarse en re-enriquecimiento)
    if enrichment.signal:
        result["signal"] = enrichment.signal

    # status: jamás se toca (el campo ni se lee aquí)

    return result
