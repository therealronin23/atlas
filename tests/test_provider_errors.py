"""
Tests para atlas.core.provider_errors — clasificación estructurada de errores
de proveedores LLM (T1 del plan T5.2/T5.3, 2026-07-23).

Cero red, cero litellm real: las excepciones se construyen a mano (clases
mock con los atributos que litellm expone: status_code, response.headers,
litellm_response_headers) para que el test sea hermético y determinista.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.provider_errors import (
    ErrorKind,
    ProviderError,
    _extract_retry_after,
    classify_provider_error,
)


# ---------------------------------------------------------------------------
# Excepciones falsas — mismo shape que las de litellm/OpenAI pero sin
# depender de esos paquetes en el test.
# ---------------------------------------------------------------------------


class _FakeHeaders(dict[str, str]):
    """dict simple; litellm/httpx usan headers case-insensitive, pero para
    el test alcanza con claves en minúscula tal cual las manda el proveedor."""


class _FakeResponse:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = _FakeHeaders(headers or {})


class _FakeProviderException(Exception):
    """Base con los atributos opcionales que litellm añade a sus excepciones."""

    def __init__(
        self,
        message: str = "boom",
        *,
        status_code: int | None = None,
        response: _FakeResponse | None = None,
        litellm_response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        if response is not None:
            self.response = response
        if litellm_response_headers is not None:
            self.litellm_response_headers = litellm_response_headers


# Clases con nombres que imitan las reales de litellm — usadas para probar
# el respaldo por nombre-de-clase cuando no hay status_code.
class RateLimitError(_FakeProviderException):
    pass


class AuthenticationError(_FakeProviderException):
    pass


class PermissionDeniedError(_FakeProviderException):
    pass


class NotFoundError(_FakeProviderException):
    pass


class BadRequestError(_FakeProviderException):
    pass


class ContextWindowExceededError(_FakeProviderException):
    pass


class ServiceUnavailableError(_FakeProviderException):
    pass


class InternalServerError(_FakeProviderException):
    pass


class Timeout(_FakeProviderException):
    pass


class APIConnectionError(_FakeProviderException):
    pass


class SomeWeirdVendorError(_FakeProviderException):
    pass


# ---------------------------------------------------------------------------
# classify_provider_error — mapeo status_code -> ErrorKind
# ---------------------------------------------------------------------------


def test_429_status_code_maps_to_rate_limit_retryable() -> None:
    exc = SomeWeirdVendorError("too many requests", status_code=429)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.RATE_LIMIT
    assert result.retryable is True
    assert result.status_code == 429


@pytest.mark.parametrize("code", [401, 403])
def test_401_403_status_code_maps_to_auth_not_retryable(code: int) -> None:
    exc = SomeWeirdVendorError("nope", status_code=code)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.AUTH
    assert result.retryable is False
    assert result.status_code == code


@pytest.mark.parametrize("code", [404, 410])
def test_404_410_status_code_maps_to_not_found_not_retryable(code: int) -> None:
    exc = SomeWeirdVendorError("gone", status_code=code)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.NOT_FOUND
    assert result.retryable is False
    assert result.status_code == code


@pytest.mark.parametrize("code", [500, 502, 503, 599])
def test_5xx_status_code_maps_to_server_retryable(code: int) -> None:
    exc = SomeWeirdVendorError("server exploded", status_code=code)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.SERVER
    assert result.retryable is True
    assert result.status_code == code


def test_400_with_context_message_maps_to_context_length_not_retryable() -> None:
    exc = BadRequestError(
        "This model's maximum context length is 8192 tokens", status_code=400
    )
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.CONTEXT_LENGTH
    assert result.retryable is False
    assert result.status_code == 400


def test_400_without_context_hint_falls_back_to_unknown() -> None:
    exc = BadRequestError("malformed request body", status_code=400)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.UNKNOWN
    assert result.retryable is False


# ---------------------------------------------------------------------------
# classify_provider_error — respaldo por nombre de clase (sin status_code)
# ---------------------------------------------------------------------------


def test_service_unavailable_error_without_status_code_maps_to_server() -> None:
    exc = ServiceUnavailableError("upstream down")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.SERVER
    assert result.retryable is True
    assert result.status_code is None


def test_internal_server_error_without_status_code_maps_to_server() -> None:
    exc = InternalServerError("500 from upstream")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.SERVER
    assert result.retryable is True


def test_timeout_maps_to_timeout_retryable() -> None:
    exc = Timeout("request timed out")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.TIMEOUT
    assert result.retryable is True
    assert result.status_code is None


def test_api_connection_error_maps_to_connection_retryable() -> None:
    exc = APIConnectionError("connection refused")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.CONNECTION
    assert result.retryable is True
    assert result.status_code is None


def test_rate_limit_error_class_name_without_status_code_maps_to_rate_limit() -> None:
    exc = RateLimitError("slow down")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.RATE_LIMIT
    assert result.retryable is True


def test_authentication_error_class_name_maps_to_auth() -> None:
    exc = AuthenticationError("invalid api key")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.AUTH
    assert result.retryable is False


def test_permission_denied_error_class_name_maps_to_auth() -> None:
    exc = PermissionDeniedError("forbidden")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.AUTH
    assert result.retryable is False


def test_not_found_error_class_name_maps_to_not_found() -> None:
    exc = NotFoundError("model does not exist")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.NOT_FOUND
    assert result.retryable is False


def test_context_window_exceeded_error_class_name_maps_to_context_length() -> None:
    exc = ContextWindowExceededError("too many tokens")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.CONTEXT_LENGTH
    assert result.retryable is False


def test_status_code_takes_priority_over_misleading_class_name() -> None:
    # nombre de clase sugiere rate limit pero el status_code real es 404 —
    # status_code manda.
    exc = RateLimitError("actually not found", status_code=404)
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.NOT_FOUND
    assert result.retryable is False


# ---------------------------------------------------------------------------
# classify_provider_error — excepción totalmente desconocida
# ---------------------------------------------------------------------------


def test_unknown_exception_without_status_code_or_headers_is_unknown() -> None:
    exc = SomeWeirdVendorError("no idea what happened")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.UNKNOWN
    assert result.retryable is False
    assert result.status_code is None
    assert result.retry_after_s is None


def test_plain_python_exception_never_raises_and_is_unknown() -> None:
    exc = ValueError("just a plain exception, no litellm attrs at all")
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.UNKNOWN
    assert result.retryable is False
    assert result.retry_after_s is None


def test_raw_message_preserves_str_of_exception() -> None:
    exc = SomeWeirdVendorError("descriptive message", status_code=429)
    result = classify_provider_error(exc)
    assert "descriptive message" in result.raw_message


def test_result_is_provider_error_dataclass_instance() -> None:
    exc = SomeWeirdVendorError("x", status_code=429)
    result = classify_provider_error(exc)
    assert isinstance(result, ProviderError)


# ---------------------------------------------------------------------------
# _extract_retry_after — lectura defensiva de headers
# ---------------------------------------------------------------------------


def test_extract_retry_after_reads_retry_after_header_from_response() -> None:
    exc = RateLimitError(
        "slow down", status_code=429, response=_FakeResponse({"retry-after": "30"})
    )
    assert _extract_retry_after(exc) == 30.0


def test_extract_retry_after_falls_back_to_ratelimit_reset_requests() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        response=_FakeResponse({"x-ratelimit-reset-requests": "12.5"}),
    )
    assert _extract_retry_after(exc) == 12.5


def test_extract_retry_after_falls_back_to_ratelimit_reset_tokens() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        response=_FakeResponse({"x-ratelimit-reset-tokens": "7"}),
    )
    assert _extract_retry_after(exc) == 7.0


def test_extract_retry_after_prefers_retry_after_over_ratelimit_reset() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        response=_FakeResponse(
            {"retry-after": "5", "x-ratelimit-reset-requests": "999"}
        ),
    )
    assert _extract_retry_after(exc) == 5.0


def test_extract_retry_after_reads_litellm_response_headers_attr() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        litellm_response_headers={"retry-after": "45"},
    )
    assert _extract_retry_after(exc) == 45.0


def test_extract_retry_after_prefers_response_headers_over_litellm_attr() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        response=_FakeResponse({"retry-after": "5"}),
        litellm_response_headers={"retry-after": "999"},
    )
    assert _extract_retry_after(exc) == 5.0


def test_extract_retry_after_returns_none_without_response_or_headers_attr() -> None:
    exc = RateLimitError("slow down", status_code=429)
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_never_raises_on_missing_response_attr() -> None:
    # exc.response existe pero no tiene .headers (objeto arbitrario) —
    # nunca debe lanzar.
    class _NoHeadersResponse:
        pass

    exc = RateLimitError("slow down", status_code=429)
    exc.response = _NoHeadersResponse()  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_never_raises_on_plain_exception() -> None:
    exc = ValueError("nothing here")
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_ignores_unparseable_header_value() -> None:
    exc = RateLimitError(
        "slow down",
        status_code=429,
        response=_FakeResponse({"retry-after": "not-a-number"}),
    )
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_is_case_insensitive_on_header_name() -> None:
    exc = RateLimitError(
        "slow down", status_code=429, response=_FakeResponse({"Retry-After": "20"})
    )
    assert _extract_retry_after(exc) == 20.0


# ---------------------------------------------------------------------------
# classify_provider_error — retry_after_s se propaga al resultado completo
# ---------------------------------------------------------------------------


def test_classify_provider_error_populates_retry_after_s_on_rate_limit() -> None:
    exc = RateLimitError(
        "slow down", status_code=429, response=_FakeResponse({"retry-after": "17"})
    )
    result = classify_provider_error(exc)
    assert result.kind == ErrorKind.RATE_LIMIT
    assert result.retry_after_s == 17.0


def test_classify_provider_error_retry_after_s_none_without_headers() -> None:
    exc = SomeWeirdVendorError("timeout-ish", status_code=500)
    result = classify_provider_error(exc)
    assert result.retry_after_s is None
