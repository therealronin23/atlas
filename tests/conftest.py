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
    # Added 2026-05-27 with Hermes-Agent twin (ADR-026)
    "NVIDIA_API_KEY",
    "HF_TOKEN",
)

# Hermes REST: tests usan mock in-memory salvo tests explicitos de integracion.
# ATLAS_HERMES_LOCAL (takeover local con VPS pausado) tambien se aisla: el .env
# de produccion lo trae a 1 y cambiaria la conducta de los tests de delegacion.
_HERMES_ENV_KEYS = ("HERMES_BASE_URL", "HERMES_API_KEY", "ATLAS_HERMES_LOCAL")

# Mode overrides: si el shell del usuario tiene .env cargado con
# ATLAS_*_MODE=auto, eso anula el `mode=...` que cada test pasa al constructor
# de InferenceHub/LiteLLMEmbedder/SLMClassifier. Borrarlos garantiza que los
# tests con mode="live"/"stub" sigan siendo deterministas.
_MODE_OVERRIDES = (
    "ATLAS_INFERENCE_MODE",
    "ATLAS_EMBEDDING_MODE",
    "ATLAS_SLM_CLASSIFIER_MODE",
)

# Autonomía (ADR-039/040): el .env de producción trae ATLAS_DECIDER=autonomous
# y el cron activo — y `import litellm` hace load_dotenv() del CWD, así que esas
# claves se cuelan en os.environ de pytest. Los tests asumen HumanDecider
# (paridad HITL) salvo que cada test fije lo contrario.
_AUTONOMY_ENV_KEYS = (
    "ATLAS_DECIDER",
    "ATLAS_MAINTENANCE_SCHEDULER",
    "ATLAS_MAINTENANCE_POLL_S",
)


@pytest.fixture(autouse=True)
def _isolate_external_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        *_EXTERNAL_API_KEYS,
        *_HERMES_ENV_KEYS,
        *_MODE_OVERRIDES,
        *_AUTONOMY_ENV_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)
    # Pending approvals HMAC (tests; no secretos reales)
    monkeypatch.setenv("ATLAS_PENDING_HMAC_KEY", "test-pending-hmac-key")


@pytest.fixture(autouse=True)
def _no_real_dep_scout(monkeypatch: pytest.MonkeyPatch) -> None:
    """El _dep_cycle del scheduler consulta PyPI y dispara ValidationRunner
    (pytest+mypy reales) cuando hay bump disponible. En tests eso es red real
    + suite recursiva (cuelgue 2026-06-12). Scout nulo por defecto; cada test
    inyecta su fake vía ``orch._maintenance_dep_scout`` si ejercita el ciclo.
    test_dep_scout.py construye DepScout directamente y no pasa por aquí."""
    from types import SimpleNamespace

    from atlas.core.orchestrator import Orchestrator

    def _stub(self: Orchestrator) -> object:
        if self._maintenance_dep_scout is None:
            self._maintenance_dep_scout = SimpleNamespace(discover=lambda: [])
        return self._maintenance_dep_scout

    monkeypatch.setattr(Orchestrator, "maintenance_dep_scout", _stub)


# Note: tried adding a singleton-reset autouse fixture (GovernanceL0._instance
# = None at setup or teardown) to fix the 2-4 non-deterministic test_pending /
# test_pipeline_d failures from test pollution. Both setup-only AND
# teardown-only made things worse (more tests assume an initialized
# Governance carried over). Real fix: per-test fixtures explicitly recreating
# GovernanceL0 from the test's own tmp_path/governance.json. Deferred.
