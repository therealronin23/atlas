"""
Aislamiento de entorno para la suite de tests.

Limpia keys de proveedores externos antes de cada test para evitar que un
test descuidado golpee APIs reales si el shell del usuario tiene `.env`
cargado. La proteccion del InferenceHub (deteccion de PYTEST_CURRENT_TEST)
sigue activa como segunda barrera.
"""

from __future__ import annotations

from typing import Generator

import pytest

from atlas.core.git_env import _GIT_HOOK_ENV_VARS


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
_HERMES_ENV_KEYS = (
    "HERMES_BASE_URL",
    "HERMES_API_KEY",
    "HERMES_KANBAN_TRANSPORT",
    "ATLAS_HERMES_LOCAL",
)

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
def _isolate_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_HOOK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


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
    # 2026-07-03: default_embedder() cambió a fastembed (semántico, carga un
    # modelo ONNX real) — sin esto, cada test que active Gate D o construya
    # un LessonRecaller sin embedder explícito cargaría el modelo real,
    # ralentizando la suite entera sin necesidad (estos tests verifican
    # CABLEADO, no calidad semántica). Un test concreto que SÍ quiera probar
    # el semántico real puede seguir haciendo su propio
    # monkeypatch.setenv("ATLAS_EMBEDDER", "fastembed") dentro del test.
    monkeypatch.setenv("ATLAS_EMBEDDER", "stub")


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


@pytest.fixture(autouse=True)
def _reset_governance_singleton() -> "Generator[None, None, None]":
    """
    Garantia por test: GovernanceL0._instance nunca se cuela de un test al
    siguiente. El Orchestrator llama a GovernanceL0.initialize() en su
    constructor; si _instance ya no es None, el singleton se reutiliza con la
    config del test anterior — fuente de fallos no deterministas en
    test_pending_integrity y test_orchestrator_pipeline_d.

    La fixture limpia ANTES del test (setup) y DESPUES (teardown) para cubrir
    ambas direcciones de contaminacion. Tests que ejercen GovernanceL0
    directamente siguen pudiendo llamar a initialize() sin problema — la primera
    llamada en cada test encontrara _instance == None.

    Por que autouse y no solo en conftest de cada modulo: el singleton es
    global; hay que limpiarlo en TODOS los tests, no solo los que usan
    Orchestrator explicitamente.
    """
    import atlas.governance.governance_l0 as _g

    _g.GovernanceL0._instance = None
    yield
    _g.GovernanceL0._instance = None
