"""
Aislamiento de entorno para la suite de tests.

Limpia keys de proveedores externos antes de cada test para evitar que un
test descuidado golpee APIs reales si el shell del usuario tiene `.env`
cargado. La proteccion del InferenceHub (deteccion de PYTEST_CURRENT_TEST)
sigue activa como segunda barrera.
"""

from __future__ import annotations

import ipaddress
import os
import socket
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

# ADR-077 (2026-07-25): el .env de producción activó ATLAS_SECURITY_COUNCIL_GATE=1
# DESPUÉS de que este fichero se escribiera -- mismo mecanismo de fuga que
# _AUTONOMY_ENV_KEYS de arriba (import litellm -> load_dotenv() del CWD). Sin
# esto, 12 tests que no stubean scan_fn/audit_fn (test_authorization.py,
# test_cold_update_decider.py, test_maintenance_adopter.py,
# test_reversible_mutations.py) ven el gate real activarse a mitad de suite y
# el auditor LLM sin claves alcanzables falla cerrado -- cambia veredictos
# Allow/Deny que esos tests ya verifican sin esperar el gate.
_SECURITY_COUNCIL_ENV_KEYS = ("ATLAS_SECURITY_COUNCIL_GATE",)

# Guardia anti-recursión (041f3972, 2026-07-09): puesta en el entorno real
# cuando ESTA suite corre dentro del propio lazo de auto-build. Un test que
# ejercite self_build_tick/similares con fakes, sin limpiarla, ve un corte
# silencioso (status=nested_run_guard) en vez del comportamiento que espera
# — gap real que dejó 2 tests rotos en silencio 6 días (ver
# tests/test_maintenance_autoloop.py, fixture `orch`). Limpia por defecto
# aquí; un test que SÍ quiera probar el guard puede seguir haciendo su
# propio monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1") en el cuerpo del
# test (corre después de este autouse).
_NESTED_TEST_RUN_ENV_KEYS = ("ATLAS_NESTED_TEST_RUN",)

# 2026-07-30: tres flags de tick opt-in añadidos al .env de producción esta
# misma sesión (provider_status, provider_discovery, workbench_compliance_review)
# nunca se sumaron aquí -- mismo mecanismo de fuga que _AUTONOMY_ENV_KEYS. Se
# quedó sin efecto ~2 semanas porque una regresión aparte (5da5f5f, 2026-07-16)
# eliminó el load_dotenv() de inference_hub.py sin que nada lo notara; al
# restaurarlo (tests/test_inference_hub_dotenv.py) estos tres flags empezaron
# a colarse de verdad y rompieron test_maintenance_provider_discovery_tick.py
# (que asume "first run" == flag nunca visto) y
# TestProviderSmokeTick::test_runs_and_classifies_providers.
_MAINTENANCE_TICK_FLAG_KEYS = (
    "ATLAS_PROVIDER_STATUS",
    "ATLAS_PROVIDER_DISCOVERY",
    "ATLAS_WORKBENCH_COMPLIANCE_REVIEW",
)
_CANDIDATE_VALIDATION_ENV = "ATLAS_CANDIDATE_VALIDATION"
_OFFLINE_TEST_PUBLIC_IP = "93.184.216.34"


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
        *_SECURITY_COUNCIL_ENV_KEYS,
        *_NESTED_TEST_RUN_ENV_KEYS,
        *_MAINTENANCE_TICK_FLAG_KEYS,
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
def _reset_default_providers_state() -> None:
    """`DEFAULT_PROVIDERS` es una lista de `Provider` mutables a nivel de
    módulo -- `InferenceHub` actualiza `status`/`last_used`/`error_count`
    in-place (diseño correcto para un daemon de un solo proceso de larga
    vida, ver `inference_hub.py`). En la suite, cientos de tests comparten
    los MISMOS objetos `Provider` sin copiar; el primer test que dispare una
    llamada real o stub deja `status=OK`/`last_used` poblado para el resto
    de la sesión de pytest. Descubierto 2026-07-30 al restaurar
    `load_dotenv()` en `inference_hub.py` (la regresión de 5da5f5f llevaba
    ~2 semanas enmascarando esto sin querer): 5 tests de
    `test_maintenance_provider_discovery_tick.py`/`test_self_improvement_wiring.py`
    fallaban SOLO en combinación con otros tests, nunca en aislamiento.
    """
    from atlas.core.inference_hub import DEFAULT_PROVIDERS, ProviderStatus

    for provider in DEFAULT_PROVIDERS:
        provider.status = ProviderStatus.OK
        provider.last_used = None
        provider.error_count = 0


@pytest.fixture(autouse=True)
def _candidate_validation_uses_deterministic_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep injected-fetch tests deterministic in the networkless candidate jail.

    ``SSRFBridge`` deliberately fails closed when DNS is absent. Candidate
    validation deliberately has no network, yet most unit tests inject their
    fetcher and intend to exercise parsing or policy after that gate. Supply a
    public fixture address only in the runner's explicit test profile; real
    egress remains impossible in Bwrap and tests that patch DNS themselves
    still take precedence.
    """
    if os.environ.get(_CANDIDATE_VALIDATION_ENV) != "1":
        return

    real_getaddrinfo = socket.getaddrinfo

    def _fixture_getaddrinfo(host: object, port: object, *args: object, **kwargs: object):
        if isinstance(host, str):
            try:
                ipaddress.ip_address(host)
            except ValueError:
                return [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        (_OFFLINE_TEST_PUBLIC_IP, int(port) if isinstance(port, int) else 0),
                    )
                ]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _fixture_getaddrinfo)


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
