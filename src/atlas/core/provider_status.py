"""Atlas Core -- estado en vivo (¿outage ahora?) reportado por cada proveedor.

Pedido directo del operador (2026-07-30): "deberíamos estar sincronizados...
con la URL de estado de la red por si reportan caídas, es una llamada rápida
y barata que nos ahorra dolores de cabeza". Complementa a
`provider_discovery.py` (qué modelos SIRVE el proveedor) con "¿el proveedor
mismo está reportando una incidencia AHORA?" -- también cero inferencia, cero
tokens.

Las tres URLs de abajo se verificaron EN VIVO el 2026-07-30 (curl real, no
memoria del modelo) antes de escribir este módulo:
- Groq: https://groqstatus.com/api/v1/summary (incident.io, JSON público).
- Together: https://status.together.ai/index.json (Betterstack, patrón
  documentado ``/index.json`` sobre cualquier status page Betterstack).
- Google Cloud: https://status.cloud.google.com/incidents.json (feed propio).
  Cobertura INCIERTA para `gemini_free`: ese provider golpea
  ``generativelanguage.googleapis.com`` (API gratuita por API-key), mientras
  que el único incidente relacionado con Gemini visto en el feed el
  2026-07-30 afectaba a "Vertex Gemini API" (producto de pago de Vertex AI,
  infraestructura distinta). Se usa igualmente -- una señal parcial es mejor
  que ninguna -- pero el ``reason`` de un resultado "operational" para google
  siempre nombra esta incertidumbre explícitamente; no tratarlo como
  confirmación fuerte.

OpenRouter (SPA React Router tras reto de Cloudflare, sin endpoint JSON
descubierto) y NVIDIA NIM/build.nvidia.com (sin página de estado dedicada
encontrada) no tienen endpoint público fiable. Se declaran con
outcome="no_public_status_page" -- NUNCA se omiten en silencio, porque un
proveedor ausente del reporte parece "no monitorizado" solo si nadie lo
señala explícitamente.

Ollama (local, loopback) no es una superficie de red externa: no aplica.

Nunca lanza: toda excepción se traduce a ``outcome="unreachable"`` (mismo
principio que ``provider_discovery.py``). ``http_get`` es inyectable a
propósito; ningún test de este módulo toca red real.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.core.inference_hub import Provider

_DEFAULT_TIMEOUT_S = 8.0

_GROQ_STATUS_URL = "https://groqstatus.com/api/v1/summary"
_TOGETHER_STATUS_URL = "https://status.together.ai/index.json"
_GOOGLE_STATUS_URL = "https://status.cloud.google.com/incidents.json"

# Substrings de affected_products.title que cuentan como "afecta a Gemini" en
# el feed de Google Cloud. Deliberadamente angosto: "Vertex AI" a secas cubre
# decenas de productos no relacionados (AutoML, Feature Store, ...).
_GOOGLE_GEMINI_PRODUCT_MARKERS = ("gemini", "generative language")


def status_vendor(provider: Provider) -> str | None:
    """Vendor con página de estado pública conocida, o None si no hay una
    fiable (ver docstring del módulo). Detección por `litellm_model`/`base_url`,
    igual que `provider_discovery.discovery_kind` -- no hardcodea nombres de
    Provider concretos."""
    litellm_model = provider.litellm_model or ""
    base_url = provider.base_url or ""
    if "api.groq.com" in base_url:
        return "groq"
    if litellm_model.startswith("together_ai/") or "api.together.xyz" in base_url:
        return "together"
    if litellm_model.startswith("gemini/") or "generativelanguage.googleapis.com" in base_url:
        return "google"
    if litellm_model.startswith("openrouter/") or "openrouter.ai" in base_url:
        return "openrouter"
    if litellm_model.startswith("nvidia_nim/") or "integrate.api.nvidia.com" in base_url:
        return "nvidia"
    return None


@dataclass
class StatusResult:
    vendor: str
    outcome: str  # "ok" | "unreachable" | "no_public_status_page"
    state: str  # "operational" | "degraded" | "outage" | "unknown"
    reason: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "outcome": self.outcome,
            "state": self.state,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


def _default_http_get(url: str, *, headers: dict[str, str], timeout: float) -> Any:
    """Implementación real -- solo se ejecuta fuera de tests (ningún test de
    este módulo la ejercita: siempre inyectan `http_get`)."""
    import httpx

    return httpx.get(url, headers=headers, timeout=timeout)


def _parse_groq(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("payload no es un objeto")
    incidents = payload.get("ongoing_incidents", [])
    if not isinstance(incidents, list):
        raise ValueError("ongoing_incidents no es una lista")
    if incidents:
        names = [i.get("name", "?") for i in incidents if isinstance(i, dict)]
        return "degraded", f"incidente(s) en curso: {'; '.join(names)}"
    return "operational", "sin incidentes en curso"


def _parse_together(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("payload no es un objeto")
    state = payload["data"]["attributes"]["aggregate_state"]
    if state == "operational":
        return "operational", "aggregate_state=operational"
    return "degraded", f"aggregate_state={state}"


def _parse_google(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, list):
        raise ValueError("payload no es una lista de incidentes")
    caveat = (
        "cobertura incierta: el feed confirma 'Vertex Gemini API', no "
        "generativelanguage.googleapis.com (tier gratis)"
    )
    open_hits: list[str] = []
    for incident in payload:
        if not isinstance(incident, dict):
            continue
        if incident.get("end"):
            continue  # resuelto
        products = incident.get("affected_products", [])
        titles = [
            str(p.get("title", "")).lower()
            for p in products
            if isinstance(p, dict)
        ]
        if any(marker in title for title in titles for marker in _GOOGLE_GEMINI_PRODUCT_MARKERS):
            open_hits.append(str(incident.get("external_desc", "incidente sin descripción")))
    if open_hits:
        return "degraded", f"incidente(s) abiertos afectando Gemini: {'; '.join(open_hits)} ({caveat})"
    return "operational", f"sin incidentes abiertos afectando Gemini ({caveat})"


_STATUS_URLS: dict[str, str] = {
    "groq": _GROQ_STATUS_URL,
    "together": _TOGETHER_STATUS_URL,
    "google": _GOOGLE_STATUS_URL,
}
_PARSERS: dict[str, Callable[[Any], tuple[str, str]]] = {
    "groq": _parse_groq,
    "together": _parse_together,
    "google": _parse_google,
}


def _check_one(vendor: str, *, http_get: Callable[..., Any], timeout_s: float) -> StatusResult:
    url = _STATUS_URLS[vendor]
    try:
        response = http_get(url, headers={}, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 -- nunca lanza, se traduce a resultado
        return StatusResult(vendor=vendor, outcome="unreachable", state="unknown", reason=str(exc))

    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        return StatusResult(
            vendor=vendor, outcome="unreachable", state="unknown", reason=f"HTTP {status_code}"
        )

    try:
        payload = response.json()
        state, reason = _PARSERS[vendor](payload)
    except Exception as exc:  # noqa: BLE001 -- parseo defensivo, nunca lanza
        return StatusResult(
            vendor=vendor,
            outcome="unreachable",
            state="unknown",
            reason=f"error parseando respuesta: {exc}",
        )

    return StatusResult(vendor=vendor, outcome="ok", state=state, reason=reason)


def check_provider_status(
    providers: Sequence[Provider],
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    http_get: Callable[..., Any] | None = None,
) -> list[StatusResult]:
    """Un `StatusResult` por VENDOR distinto entre `providers` (deduplicado:
    varios providers del mismo vendor -- ej. groq_llama_70b/groq_compound/
    groq_qwen3 -- comparten una sola llamada, la página de estado es del
    vendor, no del modelo). Vendors sin página de estado pública fiable
    (`status_vendor` -> None que SÍ es un vendor externo conocido: openrouter,
    nvidia) se declaran con outcome="no_public_status_page", nunca se omiten
    en silencio. Ollama (local) no se declara -- no es una superficie de red
    externa."""
    getter = http_get if http_get is not None else _default_http_get

    seen: dict[str, None] = {}
    for provider in providers:
        vendor = status_vendor(provider)
        if vendor is not None:
            seen.setdefault(vendor, None)

    _KNOWN_UNMONITORED = {"openrouter", "nvidia"}
    results: list[StatusResult] = []
    for vendor in seen:
        if vendor in _STATUS_URLS:
            results.append(_check_one(vendor, http_get=getter, timeout_s=timeout_s))
        elif vendor in _KNOWN_UNMONITORED:
            results.append(
                StatusResult(
                    vendor=vendor,
                    outcome="no_public_status_page",
                    state="unknown",
                    reason="sin endpoint público fiable verificado (ver docstring del módulo)",
                )
            )
    return results
