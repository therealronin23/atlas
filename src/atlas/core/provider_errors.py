"""
Atlas Core — clasificación estructurada de errores de proveedores LLM.

Sustituye el substring-matching disperso que hoy vive en `inference_hub.py`
(`_classify_error`, `_is_transient`) por una única fuente de verdad:
`classify_provider_error(exc)`. Diseño (plan T5.2/T5.3, T1, 2026-07-23):

- Usa `exc.status_code` cuando existe (litellm lo añade a sus excepciones,
  heredadas de las de OpenAI); si no hay `status_code`, cae al nombre de la
  clase de la excepción como respaldo.
- `_extract_retry_after` lee `Retry-After`/`x-ratelimit-reset-*` de forma
  defensiva (`getattr` en cada paso) — nunca lanza, aunque la excepción no
  tenga ninguno de esos atributos (excepciones planas de Python incluidas).

Cero red, cero dependencia de litellm en este módulo: solo inspecciona los
atributos que la excepción YA trae puestos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorKind(str, Enum):
    RATE_LIMIT = "rate_limit"      # 429 — reintentable tras cooldown
    AUTH = "auth"                  # 401/403 — permanente, key muerta
    NOT_FOUND = "not_found"        # 404/410 — modelo decomisionado/renombrado, permanente
    CONTEXT_LENGTH = "context"     # 400 context window — permanente para ESTE request
    TIMEOUT = "timeout"            # transitorio
    SERVER = "server"              # 5xx — transitorio
    CONNECTION = "connection"      # APIConnection — transitorio
    UNKNOWN = "unknown"


@dataclass
class ProviderError:
    kind: ErrorKind
    retryable: bool
    status_code: int | None
    retry_after_s: float | None    # de header Retry-After o x-ratelimit-reset-*; None si no lo dice
    raw_message: str


# Nombres de clase (litellm/OpenAI) usados como respaldo cuando la excepción
# no trae status_code. Substrings, no igualdad exacta: litellm re-exporta
# variantes (ej. "litellm.exceptions.RateLimitError").
_AUTH_MARKERS = ("Authentication", "PermissionDenied")
_SERVER_MARKERS = ("ServiceUnavailable", "InternalServer")


def _status_based_kind(status_code: int, message: str) -> tuple[ErrorKind, bool] | None:
    """Mapeo por status_code. None si el código no es reconocido (deja que
    el caller pruebe el respaldo por nombre de clase)."""
    if status_code == 429:
        return ErrorKind.RATE_LIMIT, True
    if status_code in (401, 403):
        return ErrorKind.AUTH, False
    if status_code in (404, 410):
        return ErrorKind.NOT_FOUND, False
    if status_code == 400:
        if "context" in message.lower():
            return ErrorKind.CONTEXT_LENGTH, False
        return None
    if 500 <= status_code < 600:
        return ErrorKind.SERVER, True
    return None


def _name_based_kind(name: str) -> tuple[ErrorKind, bool] | None:
    """Respaldo por nombre de clase cuando no hay status_code (o el
    status_code no fue reconocido). None si tampoco el nombre dice nada."""
    if "RateLimit" in name:
        return ErrorKind.RATE_LIMIT, True
    if any(marker in name for marker in _AUTH_MARKERS):
        return ErrorKind.AUTH, False
    if "NotFound" in name:
        return ErrorKind.NOT_FOUND, False
    if "ContextWindow" in name:
        return ErrorKind.CONTEXT_LENGTH, False
    if any(marker in name for marker in _SERVER_MARKERS):
        return ErrorKind.SERVER, True
    if "Timeout" in name:
        return ErrorKind.TIMEOUT, True
    if "APIConnection" in name or "ConnectionError" in name:
        return ErrorKind.CONNECTION, True
    return None


def classify_provider_error(exc: BaseException) -> ProviderError:
    """Clasifica una excepción de proveedor en un ErrorKind + retryable.

    Nunca lanza: cualquier excepción (incluida una `ValueError` plana sin
    ningún atributo de litellm) cae a UNKNOWN/retryable=False.
    """
    status_code = getattr(exc, "status_code", None)
    name = type(exc).__name__
    message = str(exc)

    kind_retryable: tuple[ErrorKind, bool] | None = None
    if isinstance(status_code, int):
        kind_retryable = _status_based_kind(status_code, message)
    if kind_retryable is None:
        kind_retryable = _name_based_kind(name)
    if kind_retryable is None:
        kind_retryable = (ErrorKind.UNKNOWN, False)

    kind, retryable = kind_retryable
    retry_after_s = _extract_retry_after(exc)
    return ProviderError(
        kind=kind,
        retryable=retryable,
        status_code=status_code if isinstance(status_code, int) else None,
        retry_after_s=retry_after_s,
        raw_message=message,
    )


def _header_get(headers: Any, key: str) -> str | None:
    """Busca `key` en `headers` sin asumir su tipo — puede ser un dict
    plano, httpx.Headers (case-insensitive nativo) o cualquier objeto con
    `.get`/`.items`. Nunca lanza."""
    if headers is None:
        return None
    try:
        value = headers.get(key)
        if value is not None:
            return str(value)
    except Exception:
        pass
    try:
        for existing_key, existing_value in headers.items():
            if str(existing_key).lower() == key.lower():
                return str(existing_value)
    except Exception:
        pass
    return None


def _headers_from(exc: BaseException) -> Mapping[str, str] | Any | None:
    """Localiza el mapping de headers en `exc`, probando en orden:
    `exc.response.headers` (forma httpx que litellm hereda de OpenAI) y,
    si no está, `exc.litellm_response_headers`. Nunca lanza."""
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers is not None:
            return headers
    return getattr(exc, "litellm_response_headers", None)


def _parse_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_retry_after(exc: BaseException) -> float | None:
    """Segundos de espera sugeridos por el proveedor, o None si no hay
    ninguna señal reconocible. Orden: `retry-after` primero (estándar HTTP,
    fiable en 429); si falta, `x-ratelimit-reset-requests` y luego
    `x-ratelimit-reset-tokens` (Groq y compatibles). Nunca lanza."""
    headers = _headers_from(exc)
    if headers is None:
        return None

    retry_after = _parse_seconds(_header_get(headers, "retry-after"))
    if retry_after is not None:
        return retry_after

    for key in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        parsed = _parse_seconds(_header_get(headers, key))
        if parsed is not None:
            return parsed

    return None
