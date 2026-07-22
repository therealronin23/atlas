"""Atlas Core -- descubrimiento en vivo de modelos servidos por proveedor.

Plan `docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md` (T3).
`DEFAULT_PROVIDERS` en `inference_hub.py` es una lista editada a mano; este
módulo consulta el endpoint de "modelos disponibles" real de cada proveedor
(``GET .../models`` estilo OpenAI, o el equivalente nativo de Gemini/Ollama)
para saber qué sirve AHORA -- **cero llamadas de inferencia, cero tokens
gastados**. Es información previa al smoke (`provider_smoke.py`), que sigue
siendo necesario porque un proveedor puede *listar* un modelo que su tier no
sirve realmente (caso NIM histórico: kimi-k2.6 en `/v1/models` pero 404
"Function not found for account" al invocar).

`http_get` es inyectable a propósito: en producción golpea red real (hecho
vía `httpx`, dependencia ya declarada); en tests siempre se inyecta un fake
que devuelve payloads sintéticos -- ningún test de este módulo toca red.

Nunca lanza: toda excepción (timeout, conexión, parseo) se captura y se
traduce a un ``DiscoveryResult`` con ``outcome`` estructurado.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.core.inference_hub import Provider

# Timeout por defecto para la llamada de discovery -- barata, no es inferencia,
# no necesita la política de reintentos/backoff del hub.
_DEFAULT_TIMEOUT_S = 10.0


def discovery_kind(provider: Provider) -> str:
    """Clasifica la forma de respuesta del endpoint de modelos del proveedor.

    "openai_models"     -> Groq/OpenRouter/NVIDIA NIM/Together (``{"data":[{"id":...}]}``)
    "gemini_listmodels"  -> Gemini (nativo, ``{"models":[{"name":"models/..."}]}``)
    "ollama_tags"        -> Ollama local (nativo, ``{"models":[{"name":...}]}``)

    Detección por ``litellm_model`` (prefijo de vendor, ya presente en el
    modelo de datos) con `base_url` como respaldo -- no hardcodea nombres de
    Provider concretos, así que sobrevive a que se añadan/retiren entries.
    """
    litellm_model = provider.litellm_model or ""
    base_url = provider.base_url or ""
    if litellm_model.startswith("ollama/") or "127.0.0.1" in base_url or "localhost" in base_url:
        return "ollama_tags"
    if litellm_model.startswith("gemini/") or "generativelanguage.googleapis.com" in base_url:
        return "gemini_listmodels"
    return "openai_models"


def _is_groq(provider: Provider) -> bool:
    # Único caso openai_models cuyo base_url NO incluye ya "/v1": el Provider
    # de Groq usa base_url="https://api.groq.com" a propósito (ver
    # inference_hub.py) porque litellm antepone "groq/" al model_id, pero el
    # endpoint REST de listado real vive en "/openai/v1/models".
    return "api.groq.com" in (provider.base_url or "")


def models_url(provider: Provider, *, api_key: str | None = None) -> str:
    """Resuelve la URL real del endpoint de modelos para este proveedor.

    ``api_key`` solo se usa para Gemini (va en query string, no en header);
    para el resto se ignora aquí -- lo añade `discover_available_models` como
    header ``Authorization``.
    """
    kind = discovery_kind(provider)
    base = (provider.base_url or "").rstrip("/")
    if kind == "ollama_tags":
        return f"{base}/api/tags"
    if kind == "gemini_listmodels":
        return f"{base}/v1beta/models?key={api_key or ''}"
    if _is_groq(provider):
        return f"{base}/openai/v1/models"
    return f"{base}/models"


@dataclass
class DiscoveryResult:
    provider_name: str
    outcome: str  # "ok" | "unreachable" | "auth_failed" | "skipped"
    model_ids: list[str] = field(default_factory=list)
    reason: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "outcome": self.outcome,
            "model_ids": self.model_ids,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


def _default_http_get(url: str, *, headers: dict[str, str], timeout: float) -> Any:
    """Implementación real por defecto -- solo se ejecuta fuera de tests
    (ningún test de este módulo la ejercita: siempre inyectan `http_get`)."""
    import httpx

    return httpx.get(url, headers=headers, timeout=timeout)


def _parse_openai_models(payload: Any) -> list[str]:
    data = payload.get("data", []) if isinstance(payload, dict) else []
    return [item["id"] for item in data if isinstance(item, dict) and "id" in item]


def _parse_gemini_listmodels(payload: Any) -> list[str]:
    models = payload.get("models", []) if isinstance(payload, dict) else []
    out: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        out.append(name[len("models/") :] if name.startswith("models/") else name)
    return out


def _parse_ollama_tags(payload: Any) -> list[str]:
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return [item["name"] for item in models if isinstance(item, dict) and "name" in item]


_PARSERS: dict[str, Callable[[Any], list[str]]] = {
    "openai_models": _parse_openai_models,
    "gemini_listmodels": _parse_gemini_listmodels,
    "ollama_tags": _parse_ollama_tags,
}


def discover_available_models(
    provider: Provider,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    http_get: Callable[..., Any] | None = None,
) -> DiscoveryResult:
    """Consulta el endpoint de modelos real del proveedor. Cero inferencia.

    Nunca lanza -- toda excepción se traduce a ``outcome="unreachable"``.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    kind = discovery_kind(provider)

    api_key: str | None = None
    if provider.api_key_env is not None:
        api_key = os.environ.get(provider.api_key_env)
        if not api_key:
            return DiscoveryResult(
                provider_name=provider.name,
                outcome="skipped",
                model_ids=[],
                reason=f"{provider.api_key_env} no configurada en el entorno",
                checked_at=checked_at,
            )

    url = models_url(provider, api_key=api_key)
    headers: dict[str, str] = {}
    if api_key is not None and kind != "gemini_listmodels":
        headers["Authorization"] = f"Bearer {api_key}"

    getter = http_get if http_get is not None else _default_http_get

    try:
        response = getter(url, headers=headers, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 -- nunca lanza, se traduce a resultado
        return DiscoveryResult(
            provider_name=provider.name,
            outcome="unreachable",
            model_ids=[],
            reason=str(exc),
            checked_at=checked_at,
        )

    status_code = getattr(response, "status_code", None)
    if status_code in (401, 403):
        return DiscoveryResult(
            provider_name=provider.name,
            outcome="auth_failed",
            model_ids=[],
            reason=f"HTTP {status_code}",
            checked_at=checked_at,
        )
    if isinstance(status_code, int) and status_code >= 400:
        return DiscoveryResult(
            provider_name=provider.name,
            outcome="unreachable",
            model_ids=[],
            reason=f"HTTP {status_code}",
            checked_at=checked_at,
        )

    try:
        payload = response.json()
        model_ids = _PARSERS[kind](payload)
    except Exception as exc:  # noqa: BLE001 -- parseo defensivo, nunca lanza
        return DiscoveryResult(
            provider_name=provider.name,
            outcome="unreachable",
            model_ids=[],
            reason=f"error parseando respuesta: {exc}",
            checked_at=checked_at,
        )

    return DiscoveryResult(
        provider_name=provider.name,
        outcome="ok",
        model_ids=model_ids,
        reason="",
        checked_at=checked_at,
    )
