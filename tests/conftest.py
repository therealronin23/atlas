"""
Aislamiento de entorno para la suite de tests.

Limpia keys de proveedores externos antes de cada test para evitar que un
test descuidado golpee APIs reales si el shell del usuario tiene `.env`
cargado. La proteccion del InferenceHub (deteccion de PYTEST_CURRENT_TEST)
sigue activa como segunda barrera.
"""

from __future__ import annotations

import pytest


_EXTERNAL_API_KEYS = (
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHERAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)

# Hermes REST: tests usan mock in-memory salvo tests explicitos de integracion.
_HERMES_ENV_KEYS = ("HERMES_BASE_URL", "HERMES_API_KEY")


@pytest.fixture(autouse=True)
def _isolate_external_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (*_EXTERNAL_API_KEYS, *_HERMES_ENV_KEYS):
        monkeypatch.delenv(key, raising=False)
    # Pending approvals HMAC (tests; no secretos reales)
    monkeypatch.setenv("ATLAS_PENDING_HMAC_KEY", "test-pending-hmac-key")
