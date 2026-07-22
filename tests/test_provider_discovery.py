"""Tests de provider_discovery -- descubrimiento en vivo de modelos servidos.

Contexto (plan 2026-07-23-t5-provider-discovery-plan.md, T3): la lista de
modelos por proveedor en DEFAULT_PROVIDERS se edita a mano; discovery
consulta el endpoint real de "modelos disponibles" de cada proveedor
(NO inferencia, cero tokens) para saber qué sirve AHORA. http_get es
inyectable a propósito: ningún test de este fichero toca red real ni
importa litellm.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, Provider
from atlas.core.provider_discovery import (
    DiscoveryResult,
    discover_available_models,
    discovery_kind,
    models_url,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _groq_provider() -> Provider:
    return Provider(
        name="groq_llama_70b",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="llama-3.3-70b-versatile",
        litellm_model="groq/llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
    )


def _openrouter_provider() -> Provider:
    return Provider(
        name="openrouter_nemotron",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="nvidia/nemotron-nano-12b-v2-vl:free",
        litellm_model="openrouter/nvidia/nemotron-nano-12b-v2-vl:free",
        api_key_env="OPENROUTER_API_KEY",
    )


def _nvidia_provider() -> Provider:
    return Provider(
        name="nvidia_llama_large",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="meta/llama-3.3-70b-instruct",
        litellm_model="nvidia_nim/meta/llama-3.3-70b-instruct",
        api_key_env="NVIDIA_API_KEY",
    )


def _together_provider() -> Provider:
    return Provider(
        name="together_free",
        level=InferenceLevel.L1,
        base_url="https://api.together.xyz/v1",
        model_id="meta-llama/Llama-3-8b-chat-hf",
        litellm_model="together_ai/meta-llama/Llama-3-8b-chat-hf",
        api_key_env="TOGETHERAI_API_KEY",
    )


def _gemini_provider() -> Provider:
    return Provider(
        name="gemini_free",
        level=InferenceLevel.L0,
        base_url="https://generativelanguage.googleapis.com",
        model_id="gemini-2.5-flash",
        litellm_model="gemini/gemini-2.5-flash",
        api_key_env="GEMINI_API_KEY",
    )


def _ollama_provider() -> Provider:
    return Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        base_url="http://127.0.0.1:11434",
        model_id="qwen2.5-coder:7b",
        litellm_model="ollama/qwen2.5-coder:7b",
        api_key_env=None,
    )


# --- discovery_kind ---------------------------------------------------


@pytest.mark.parametrize(
    "provider_factory",
    [_groq_provider, _openrouter_provider, _nvidia_provider, _together_provider],
)
def test_discovery_kind_openai_models(provider_factory: Any) -> None:
    assert discovery_kind(provider_factory()) == "openai_models"


def test_discovery_kind_gemini() -> None:
    assert discovery_kind(_gemini_provider()) == "gemini_listmodels"


def test_discovery_kind_ollama() -> None:
    assert discovery_kind(_ollama_provider()) == "ollama_tags"


# --- models_url ---------------------------------------------------------


def test_models_url_groq_uses_openai_v1_prefix() -> None:
    assert models_url(_groq_provider()) == "https://api.groq.com/openai/v1/models"


def test_models_url_generic_openai_compat_appends_models() -> None:
    assert models_url(_openrouter_provider()) == "https://openrouter.ai/api/v1/models"
    assert models_url(_nvidia_provider()) == "https://integrate.api.nvidia.com/v1/models"
    assert models_url(_together_provider()) == "https://api.together.xyz/v1/models"


def test_models_url_gemini_native_query_param() -> None:
    assert (
        models_url(_gemini_provider())
        == "https://generativelanguage.googleapis.com/v1beta/models?key="
    )
    assert (
        models_url(_gemini_provider(), api_key="secret")
        == "https://generativelanguage.googleapis.com/v1beta/models?key=secret"
    )


def test_models_url_ollama_native_tags() -> None:
    assert models_url(_ollama_provider()) == "http://127.0.0.1:11434/api/tags"


# --- discover_available_models: adaptador openai_models ------------------


def test_discover_openai_models_parses_data_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")
    calls: list[dict[str, Any]] = []

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _FakeResponse(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "other"}]})

    result = discover_available_models(_groq_provider(), http_get=fake_http_get)

    assert result.outcome == "ok"
    assert result.model_ids == ["llama-3.3-70b-versatile", "other"]
    assert result.provider_name == "groq_llama_70b"
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/models"
    assert calls[0]["headers"]["Authorization"] == "Bearer gsk_fake"


# --- discover_available_models: adaptador gemini_listmodels --------------


def test_discover_gemini_strips_models_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gm_fake")

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        assert "key=gm_fake" in url
        return _FakeResponse(
            200,
            {
                "models": [
                    {"name": "models/gemini-2.5-flash"},
                    {"name": "models/gemini-2.0-pro"},
                ]
            },
        )

    result = discover_available_models(_gemini_provider(), http_get=fake_http_get)

    assert result.outcome == "ok"
    assert result.model_ids == ["gemini-2.5-flash", "gemini-2.0-pro"]


# --- discover_available_models: adaptador ollama_tags --------------------


def test_discover_ollama_tags_parses_name() -> None:
    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        assert url == "http://127.0.0.1:11434/api/tags"
        return _FakeResponse(200, {"models": [{"name": "qwen2.5-coder:7b"}, {"name": "phi-4"}]})

    result = discover_available_models(_ollama_provider(), http_get=fake_http_get)

    assert result.outcome == "ok"
    assert result.model_ids == ["qwen2.5-coder:7b", "phi-4"]


# --- outcome: skipped / auth_failed / unreachable ------------------------


def test_discover_skipped_without_api_key_never_calls_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        raise AssertionError("http_get no debe llamarse sin API key configurada")

    result = discover_available_models(_groq_provider(), http_get=fake_http_get)

    assert result.outcome == "skipped"
    assert result.model_ids == []
    assert "GROQ_API_KEY" in result.reason


def test_discover_auth_failed_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(401, {"error": "invalid key"})

    result = discover_available_models(_groq_provider(), http_get=fake_http_get)

    assert result.outcome == "auth_failed"
    assert result.model_ids == []


def test_discover_unreachable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        raise TimeoutError("timed out")

    result = discover_available_models(_groq_provider(), http_get=fake_http_get)

    assert result.outcome == "unreachable"
    assert result.model_ids == []
    assert "timed out" in result.reason


def test_discover_unreachable_on_connection_error_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        raise ConnectionError("connection refused")

    result = discover_available_models(_groq_provider(), http_get=fake_http_get)

    assert result.outcome == "unreachable"


def test_discover_ollama_attempted_without_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama tiene api_key_env=None -- nunca debe caer en 'skipped'."""
    calls: list[str] = []

    def fake_http_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(200, {"models": []})

    result = discover_available_models(_ollama_provider(), http_get=fake_http_get)

    assert result.outcome == "ok"
    assert len(calls) == 1


def test_discover_result_default_checked_at_is_populated() -> None:
    result = DiscoveryResult(
        provider_name="p",
        outcome="skipped",
        model_ids=[],
        reason="no key",
    )
    assert result.checked_at  # default_factory rellena algo no vacío
    assert result.to_dict()["provider_name"] == "p"
