"""Atlas Core -- estado en vivo (¿outage ahora?) reportado por cada proveedor.

Pedido directo del operador (2026-07-30): "deberíamos estar sincronizados...
con la URL de estado de la red por si reportan caídas, es una llamada rápida
y barata que nos ahorra dolores de cabeza". Complementa a
`provider_discovery.py` (qué modelos SIRVE el proveedor) con "¿el proveedor
mismo está reportando una incidencia AHORA?" -- también cero inferencia, cero
tokens.

Las URLs de abajo se verificaron EN VIVO el 2026-07-30 (curl/browser real, no
memoria del modelo) antes de escribir este módulo:
- Groq: https://groqstatus.com/api/v1/summary (incident.io, JSON público).
- Together: https://status.together.ai/index.json (Betterstack, patrón
  documentado ``/index.json`` sobre cualquier status page Betterstack).
- Google: https://aistudio.google.com/status -- LA página de estado real de
  "Google AI Studio and the Gemini API" (incidentes de ListModels, claves de
  API, límites de modelo: la superficie exacta que golpea `gemini_free` via
  ``generativelanguage.googleapis.com``). Descartada a propósito la primera
  candidata (`status.cloud.google.com/incidents.json`): esa solo confirmaba
  "Vertex Gemini API" (producto de pago, infraestructura distinta), nunca la
  API gratuita. La página de AI Studio no expone JSON -- devuelve un shell
  vacío a curl/httpx, los datos se renderizan con JS -- así que se lee vía
  navegador real (Playwright, ya dependencia del proyecto para browser
  testing; no es una dependencia nueva) en vez de un GET plano. Decisión del
  operador 2026-07-30: preferir cobertura correcta sobre "barato" para este
  vendor específico.

OpenRouter: la página web (SPA React Router tras reto de Cloudflare) no
expone JSON, pero SU MECANISMO DE SUSCRIPCIÓN documentado sí --
https://status.openrouter.ai/incidents.rss, XML plano, sin reto, verificado
en vivo. Esto NO es sortear el bot-detection: es el endpoint que la propia
página ofrece para monitorización programática. NVIDIA NIM/build.nvidia.com
sigue sin página de estado dedicada encontrada tras dos búsquedas. Los
vendors sin endpoint utilizable se declaran con
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
_GOOGLE_AI_STUDIO_STATUS_URL = "https://aistudio.google.com/status"
_OPENROUTER_RSS_URL = "https://status.openrouter.ai/incidents.rss"

# Palabras de estado CERRADO observadas en vivo el 2026-07-30 en el feed real
# (RESOLVED, COMPLETED). Deliberadamente una lista de CIERRE, no de apertura:
# nunca se ha observado un incidente abierto en el feed para confirmar el
# vocabulario exacto de "en curso" (INVESTIGATING/IDENTIFIED/MONITORING son
# la convención habitual de Statuspage, pero este generador es OnlineOrNot,
# no confirmado que use las mismas palabras). Cualquier estado que NO esté en
# el set de cierre se trata como no-confirmado-resuelto -> degraded, en vez
# de adivinar qué palabras significan "abierto".
_OPENROUTER_CLOSED_STATES = {"RESOLVED", "COMPLETED"}

# Frase exacta observada en vivo el 2026-07-30. Si la maquetación cambia y
# esta frase desaparece sin que aparezca un indicador de degradación
# reconocido, se declara unreachable -- nunca se asume "operational" por
# defecto (unknown > mentir).
_GOOGLE_OPERATIONAL_PHRASE = "All Systems Operational"
_GOOGLE_DEGRADED_MARKERS = ("outage", "degraded", "disruption", "incident")


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


def _parse_google_ai_studio_text(text: str) -> tuple[str, str]:
    """Parseo textual deliberadamente conservador (no hay JSON, ver docstring
    del módulo): SOLO declara "operational" ante la frase exacta observada en
    vivo. Si no aparece pero SÍ aparece un marcador de degradación conocido,
    "degraded" con el fragmento como evidencia. Si no aparece ninguna de las
    dos -- la maquetación cambió de forma que no se reconoce -- se lanza para
    que el caller lo traduzca a "unreachable": no hay lectura honesta posible."""
    if _GOOGLE_OPERATIONAL_PHRASE in text:
        return "operational", f"página reporta '{_GOOGLE_OPERATIONAL_PHRASE}'"
    lowered = text.lower()
    for marker in _GOOGLE_DEGRADED_MARKERS:
        if marker in lowered:
            idx = lowered.index(marker)
            snippet = text[max(0, idx - 40): idx + 60].strip().replace("\n", " ")
            return "degraded", snippet
    raise ValueError(
        "no se encontró ni la frase operational ni un marcador de "
        "degradación reconocido -- maquetación cambiada, no se puede leer"
    )


def _default_browser_fetch(url: str) -> str:
    """Implementación real -- solo se ejecuta fuera de tests (ningún test de
    este módulo la ejercita: siempre inyectan `browser_fetch`). Playwright ya
    es dependencia del proyecto (browser testing); no es una dependencia
    nueva. `aistudio.google.com` se admite explícitamente vía `extra_allowed`
    del SSRFBridge -- allowlist curada, no se amplía el default global."""
    import os
    from pathlib import Path

    from atlas.security.ssrf_bridge import SSRFBridge
    from atlas.tools.browser import BrowserTool

    workspace = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    bridge = SSRFBridge(extra_allowed={"aistudio.google.com"})
    bt = BrowserTool(workspace=workspace, bridge=bridge)
    try:
        return bt.navigate(url).text
    finally:
        bt.close()


_STATUS_URLS: dict[str, str] = {
    "groq": _GROQ_STATUS_URL,
    "together": _TOGETHER_STATUS_URL,
}
_PARSERS: dict[str, Callable[[Any], tuple[str, str]]] = {
    "groq": _parse_groq,
    "together": _parse_together,
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


def _check_google(*, browser_fetch: Callable[[str], str]) -> StatusResult:
    try:
        text = browser_fetch(_GOOGLE_AI_STUDIO_STATUS_URL)
        state, reason = _parse_google_ai_studio_text(text)
    except Exception as exc:  # noqa: BLE001 -- nunca lanza, se traduce a resultado
        return StatusResult(vendor="google", outcome="unreachable", state="unknown", reason=str(exc))
    return StatusResult(vendor="google", outcome="ok", state=state, reason=reason)


def _parse_openrouter_rss(xml_text: str) -> tuple[str, str]:
    """El feed viene en orden reverso-cronológico (más reciente primero,
    verificado en vivo). Solo importa el PRIMER <item>: es el último evento
    reportado, sea incidente o mantenimiento. Feed vacío (sin items) = sin
    historial de incidentes = operational."""
    import re
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)  # noqa: S314 -- feed público, no ejecuta nada
    items = root.findall(".//item")
    if not items:
        return "operational", "feed sin incidentes registrados"

    first = items[0]
    title = (first.findtext("title") or "").strip()
    description = first.findtext("description") or ""
    match = re.search(r"<strong>([A-Z ]+)</strong>", description)
    status_word = match.group(1).strip() if match else ""

    if status_word in _OPENROUTER_CLOSED_STATES:
        return "operational", f"último incidente ({title!r}) en estado {status_word}"
    return "degraded", f"{title}: estado {status_word or '(no reconocido)'} -- no confirmado resuelto"


def _check_openrouter(*, rss_get: Callable[..., Any], timeout_s: float) -> StatusResult:
    try:
        response = rss_get(_OPENROUTER_RSS_URL, headers={}, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 -- nunca lanza, se traduce a resultado
        return StatusResult(vendor="openrouter", outcome="unreachable", state="unknown", reason=str(exc))

    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        return StatusResult(
            vendor="openrouter", outcome="unreachable", state="unknown", reason=f"HTTP {status_code}"
        )
    try:
        state, reason = _parse_openrouter_rss(response.text)
    except Exception as exc:  # noqa: BLE001 -- parseo defensivo, nunca lanza
        return StatusResult(
            vendor="openrouter", outcome="unreachable", state="unknown",
            reason=f"error parseando el feed RSS: {exc}",
        )
    return StatusResult(vendor="openrouter", outcome="ok", state=state, reason=reason)


def check_provider_status(
    providers: Sequence[Provider],
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    http_get: Callable[..., Any] | None = None,
    browser_fetch: Callable[[str], str] | None = None,
    rss_get: Callable[..., Any] | None = None,
) -> list[StatusResult]:
    """Un `StatusResult` por VENDOR distinto entre `providers` (deduplicado:
    varios providers del mismo vendor -- ej. groq_gpt_oss_120b/groq_compound/
    groq_qwen3 -- comparten una sola llamada, la página de estado es del
    vendor, no del modelo). Vendors sin página de estado pública fiable
    (`status_vendor` -> None que SÍ es un vendor externo conocido: nvidia) se
    declaran con outcome="no_public_status_page", nunca se omiten en
    silencio. Ollama (local) no se declara -- no es una superficie de red
    externa. `google` usa `browser_fetch` (Playwright, ver
    `_default_browser_fetch`), NUNCA `http_get` -- su página no expone JSON.
    `openrouter` usa `rss_get` contra su feed de suscripción -- ver
    `_check_openrouter`."""
    getter = http_get if http_get is not None else _default_http_get
    browser_getter = browser_fetch if browser_fetch is not None else _default_browser_fetch
    rss_getter = rss_get if rss_get is not None else _default_http_get

    seen: dict[str, None] = {}
    for provider in providers:
        vendor = status_vendor(provider)
        if vendor is not None:
            seen.setdefault(vendor, None)

    _KNOWN_UNMONITORED = {"nvidia"}
    results: list[StatusResult] = []
    for vendor in seen:
        if vendor == "google":
            results.append(_check_google(browser_fetch=browser_getter))
        elif vendor == "openrouter":
            results.append(_check_openrouter(rss_get=rss_getter, timeout_s=timeout_s))
        elif vendor in _STATUS_URLS:
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
