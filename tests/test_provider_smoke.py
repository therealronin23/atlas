"""Tests de ProviderChainSmoke — política de probe acotada.

2026-07-22: el smoke diario heredaba la política de producción del hub
(timeout 120s × 3 intentos, Timeout clasificado transitorio) y un solo
proveedor colgado (nvidia_mistral_medium) retuvo la pasada 18 minutos
medidos (latency_ms=1087936 en provider_smoke_state.json). Un probe
responde "¿vive?" en segundos: timeout corto, cero reintentos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.core.inference_hub import (
    InferenceLevel,
    InferenceResponse,
    Provider,
)
from atlas.core.self_maintenance.provider_smoke import (
    _PROBE_MAX_RETRIES,
    _PROBE_TIMEOUT_S,
    ProviderChainSmoke,
)


def _provider(name: str = "p1") -> Provider:
    return Provider(
        name=name,
        level=InferenceLevel.L1,
        base_url="https://example.invalid",
        model_id="m",
        litellm_model="prov/m",
        api_key_env="X_API_KEY",
        context_tokens=1000,
    )


def _pong(name: str = "p1") -> InferenceResponse:
    return InferenceResponse(
        text="pong",
        provider=name,
        model="m",
        level=InferenceLevel.L1,
        latency_ms=5,
        success=True,
        mode="live",
    )


def test_probe_requests_carry_bounded_policy() -> None:
    hub = MagicMock()
    hub.probe_provider.return_value = _pong()
    smoke = ProviderChainSmoke(hub=hub, providers=[_provider()])

    smoke.run()

    request = hub.probe_provider.call_args.args[1]
    assert request.timeout_s == _PROBE_TIMEOUT_S
    assert request.max_retries == _PROBE_MAX_RETRIES


def test_probe_worst_case_is_bounded_in_seconds_not_minutes() -> None:
    # Contrato del smoke: peor caso POR PROVEEDOR <= 60s. Con la política de
    # producción (120s × 3) el peor caso era 6+ min teóricos y 18 min medidos.
    assert _PROBE_TIMEOUT_S * (_PROBE_MAX_RETRIES + 1) <= 60.0
