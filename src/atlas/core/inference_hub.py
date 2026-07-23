"""
Atlas Core — InferenceHub
Router de modelos con pool multi-cuenta y fallback chain.

Niveles:
  L-det  -> Sin LLM (herramienta determinista, fuera del hub)
  L0     -> Modelo local (Ollama: Qwen-2.5-coder, Phi-4)
  L1     -> API gratuita (Groq, OpenRouter free, Together free, Gemini free)
  L2     -> Frontier (no usado en v0.2; reservado)

Modo de operacion:
  - "auto" (default): live cuando hay key del proveedor + litellm + no en pytest;
                       stub en cualquier otro caso. Decision por proveedor.
  - "live": fuerza llamada real (falla si no hay key o litellm).
  - "stub": fuerza respuesta simulada.

ADR-016: LiteLLM como capa de abstraccion sobre proveedores.
"""

from __future__ import annotations

import os
import random
import time
import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from atlas.core.provider_errors import ErrorKind, classify_provider_error

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger
    from atlas.transparency.gateway import TransparencyGateway
    from atlas.transparency.client_cosign import APIResponse

# Silenciar warnings cosmeticos de LiteLLM (bedrock/sagemaker pre-load, etc).
# Se debe hacer ANTES del import porque algunos warnings se emiten al cargar el modulo.
# No afecta a la chain Groq/OpenRouter/Together/Gemini que si usamos.
import logging as _logging  # noqa: E402

_logging.getLogger("LiteLLM").setLevel(_logging.ERROR)
_logging.getLogger("litellm").setLevel(_logging.ERROR)

litellm: Any | None = None
_HAS_LITELLM = importlib.util.find_spec("litellm") is not None


def _litellm_module() -> Any:
    """Import LiteLLM only for a real provider call."""
    global litellm
    if litellm is None:
        if not _HAS_LITELLM:
            raise RuntimeError("litellm no instalado")
        litellm = importlib.import_module("litellm")
        try:
            setattr(litellm, "suppress_debug_info", True)
        except Exception:  # pragma: no cover
            pass
    return litellm


RATE_LIMIT_COOLDOWN_S = 60.0

# Reintento ante transitorios (503/500/timeout/conexión). Constantes de módulo
# diseñadas-para-promover: el día que un Provider concreto necesite otra política
# (medido), se promueven a campo de Provider con estas como default — cambio aditivo.
INFER_MAX_RETRIES = 2          # reintentos extra → 3 intentos totales
INFER_RETRY_BASE_S = 0.5       # backoff: intento k espera ~BASE*2**(k-1) + jitter
INFER_REQUEST_TIMEOUT_S = 120.0  # tope duro por llamada: un proveedor colgado no
                                 # puede bloquear al caller (Cónclave >20min, 2026-07-17)

# T5.2/T5.3 T2 (2026-07-23): fuente única de verdad para "¿esta excepción se
# puede reintentar YA, dentro del mismo bucle de intentos?" — delega en
# provider_errors.classify_provider_error, que lee status_code/nombre de
# clase. Sustituye el substring-matching disperso que vivía aquí
# (_TRANSIENT_MARKERS) y en _classify_error.
# RATE_LIMIT es retryable=True para classify_provider_error (el request puede
# triunfar más tarde), pero el hub lo maneja con SU PROPIO mecanismo —cooldown
# `_rate_limited_until` + fallback a otro proveedor + `wait_for_ratelimit`—
# en vez del backoff corto (0.5-2s) de este bucle; comportamiento previo
# intacto (RateLimit nunca estuvo en _TRANSIENT_MARKERS, así se evita quemar
# 3 intentos contra un 429 que va a tardar minutos en abrir).
def _is_transient(exc: BaseException) -> bool:
    pe = classify_provider_error(exc)
    return pe.retryable and pe.kind is not ErrorKind.RATE_LIMIT


# T5 (2026-07-23, técnica disecada de OpenHands-SDK agent.py::step()):
# CONTEXT_LENGTH era un fallo terminal (classify_provider_error lo marca
# retryable=False y así debe seguir siendo dentro del bucle de intentos por
# proveedor — reintentar el MISMO payload no ayuda). Lo que faltaba era un
# nivel por encima: condensar la historia y reintentar UNA vez con menos
# contexto. Recorte determinista por presupuesto de tokens (aproximado por
# caracteres, sin tiktoken ni LLM adicional — ADR "no new deps sin
# aprobación"): preserva mensajes de sistema y los N más recientes, descarta
# los más antiguos primero.
_CONTEXT_CONDENSE_KEEP_LAST = 4
_CONTEXT_CONDENSE_TOKEN_BUDGET = 4000


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _effective_messages(request: "InferenceRequest") -> list[dict[str, Any]]:
    """Misma construcción prompt/context->messages que _call_provider_real
    (ADR-031): si el caller ya trae `messages`, se usan tal cual."""
    if request.messages is not None:
        return list(request.messages)
    messages: list[dict[str, Any]] = [{"role": "user", "content": request.prompt}]
    if request.context:
        messages.insert(0, {"role": "system", "content": request.context})
    return messages


def _condense_messages(
    messages: list[dict[str, Any]],
    *,
    budget_tokens: int = _CONTEXT_CONDENSE_TOKEN_BUDGET,
    keep_last: int = _CONTEXT_CONDENSE_KEEP_LAST,
) -> list[dict[str, Any]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    protected_tail = rest[-keep_last:] if len(rest) > keep_last else rest
    droppable = rest[: len(rest) - len(protected_tail)]

    def _total(msgs: list[dict[str, Any]]) -> int:
        return sum(_approx_tokens(str(m.get("content", ""))) for m in msgs)

    while droppable and _total(system + droppable + protected_tail) > budget_tokens:
        droppable.pop(0)  # descarta el más antiguo primero

    return system + droppable + protected_tail


def _condensed_request(request: "InferenceRequest") -> "InferenceRequest | None":
    """None si condensar no cambiaría nada (historia ya mínima) — evita
    reintentar con una petición idéntica que fallará igual."""
    messages = _effective_messages(request)
    condensed = _condense_messages(messages)
    if condensed == messages:
        return None
    return replace(request, messages=condensed)


class InferenceLevel(str, Enum):
    L_DET = "L-det"
    L0    = "L0"
    L1    = "L1"
    L2    = "L2"


class ProviderStatus(str, Enum):
    OK          = "ok"
    DEGRADED    = "degraded"
    DOWN        = "down"
    RATELIMITED = "rate_limited"


@dataclass
class Provider:
    name: str
    level: InferenceLevel
    base_url: str
    model_id: str
    litellm_model: str = ""           # ej "groq/llama-3.3-70b-versatile"
    api_key_env: str | None = None    # ej "GROQ_API_KEY"; None para Ollama
    free_tier: bool = True
    rpm_limit: int = 30
    context_tokens: int = 8192
    account_pool: list[str] = field(default_factory=list)
    extra_body: dict[str, Any] = field(default_factory=dict)  # params extra para litellm (ej. thinking:False)
    status: ProviderStatus = ProviderStatus.OK
    last_used: str | None = None
    error_count: int = 0
    # Roles explícitos (lazo 4, patrón validado 4x independientemente: Continue.dev
    # config.yaml roles=chat/edit/apply/embed, Cline Plan/Act con modelo distinto por
    # modo, Cursor apply-model separado, Aider --architect). "edit" = genera diffs/
    # SEARCH-REPLACE (razonamiento fuerte); "apply" = aplica un cambio ya decidido
    # (mecánico, barato/rápido); "chat" = conversación/planificación general.
    # Soft-preference: infer_for_role() cae a candidatos por nivel si ningún
    # provider del nivel pedido tiene el rol — nunca falla por falta de tag.
    roles: tuple[str, ...] = ()
    # 2026-07-08: capacidad de tool-calling. Un request con `tools` se salta
    # los providers marcados False, y si un provider responde "tool calling is
    # not supported" el hub lo marca False EN CALIENTE (autoaprendizaje) para
    # no volver a quemar una llamada ahí — incidente real: groq_compound
    # rechazaba tools en cada pasada del ToolCoder delegado.
    supports_tools: bool = True


@dataclass
class InferenceRequest:
    prompt: str
    level: InferenceLevel = InferenceLevel.L1
    max_tokens: int = 1024
    temperature: float = 0.1
    context: str = ""
    task_id: str | None = None
    # ADR-031: tool-calling agéntico. Si `tools` está presente se pasa a la
    # API del proveedor. Si `messages` está presente, sustituye a la
    # construcción prompt/context (para continuar una conversación multi-turno).
    tools: list[dict[str, Any]] | None = None
    messages: list[dict[str, Any]] | None = None
    tool_choice: str = "auto"
    # 2026-07-08 (absorción robustez Codex/Claude-harness): si True y TODA la
    # cadena cae rate-limitada, el hub espera al cooldown más próximo (cap
    # 120s) y re-camina la cadena hasta 2 veces más en vez de devolver
    # all_failed. Pensado para lazos largos (ToolCoder): esperar 60s es
    # infinitamente mejor que perder toda la tarea. Default False: las
    # llamadas interactivas no deben colgarse.
    wait_for_ratelimit: bool = False
    # 2026-07-22: overrides por-request de la política de llamada (promoción
    # medida de las constantes de módulo, ver comentario en INFER_MAX_RETRIES):
    # el smoke diario colgó 18 min en un solo proveedor (nvidia_mistral_medium,
    # Timeout×3 intentos×~6min) heredando la política de producción. None =
    # constantes de módulo, sin cambio de comportamiento para callers previos.
    timeout_s: float | None = None
    max_retries: int | None = None


@dataclass
class InferenceResponse:
    text: str
    provider: str
    model: str
    level: InferenceLevel
    latency_ms: int
    success: bool
    error: str | None = None
    tokens_used: int = 0
    mode: str = "stub"
    # ADR-031: si el modelo pide herramientas, vienen aquí normalizadas a
    # {id, name, arguments(str JSON)}. Vacío = respuesta final (sin loop).
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    # Protocolo de completitud (ADR-053) — presente cuando el hub tiene gateway
    api_response: "APIResponse | None" = field(default=None, repr=False)
    # T5.2/T5.3 T2 (2026-07-23): clasificación estructurada del error (si lo
    # hubo), poblada desde provider_errors.classify_provider_error. Aditivos
    # con default — no rompen construcciones existentes del dataclass.
    error_kind: str | None = None
    retry_after_s: float | None = None
    retryable: bool = False


DEFAULT_PROVIDERS: list[Provider] = [
    # L1 — Groq (rate-limit gratis para siempre; verificar IDs en console.groq.com/docs/models)
    # 2026-06-27: gpt-oss-120b devuelve contenido vacío → revertido a llama-3.3-70b-versatile
    Provider(
        name="groq_llama_70b",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="llama-3.3-70b-versatile",
        litellm_model="groq/llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        rpm_limit=30,
        context_tokens=128000,
        roles=("chat", "apply"),  # rápido/gratis; débil en multi-archivo (lección G0.7)
    ),
    # 2026-06-27: "compound-beta" fue renombrado por Groq a "compound" (la API
    # nombra el modelo literalmente "groq/compound", de ahí el prefijo doble).
    # Prove-it en vivo: compound-beta da 404, groq/groq/compound responde.
    Provider(
        name="groq_compound",
        level=InferenceLevel.L0,  # modelo de búsqueda, no sigue SEARCH/REPLACE; excluido de workers L1
        base_url="https://api.groq.com",
        model_id="groq/compound",
        litellm_model="groq/groq/compound",
        api_key_env="GROQ_API_KEY",
        rpm_limit=30,
        context_tokens=131072,
        # Verificado en vivo 2026-07-08: Groq rechaza tools con este modelo.
        supports_tools=False,
    ),
    # 2026-06-27: qwen3-32b → qwen3.6-27b (más reciente, prove-it en vivo OK).
    Provider(
        name="groq_qwen3",
        level=InferenceLevel.L0,  # thinking no deshabilitrable en Groq; excluido de workers L1
        base_url="https://api.groq.com",
        model_id="qwen/qwen3.6-27b",
        litellm_model="groq/qwen/qwen3.6-27b",
        api_key_env="GROQ_API_KEY",
        rpm_limit=30,
        context_tokens=32768,
    ),
    # 2026-07-08: groq_deepseek_r1 (deepseek-r1-distill-llama-70b) RETIRADO de
    # la cadena — Groq lo decomisionó (jun 2026) y dejarlo garantizaba una
    # llamada fallida real cada vez que el fallback llegaba aquí (verificado en
    # vivo: ToolCoder delegado murió con model_decommissioned en la 1ª llamada).
    Provider(
        name="openrouter_nemotron",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="nvidia/nemotron-nano-12b-v2-vl:free",
        litellm_model="openrouter/nvidia/nemotron-nano-12b-v2-vl:free",
        api_key_env="OPENROUTER_API_KEY",
        account_pool=["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"],
        rpm_limit=20,
        context_tokens=128000,
        roles=("chat",),
    ),
    # 2026-07-08: openrouter_liquid (liquid/lfm-2.5-1.2b-instruct:free) RETIRADO
    # — NotFound verificado en vivo (OpenRouter eliminó el endpoint); dejarlo
    # quemaba una llamada fallida por pasada del fallback.
    # 2026-06-27: Qwen3-Coder-480B gratis en OpenRouter (roles edit); ya entonces
    # "temporarily rate-limited upstream" con frecuencia.
    # 2026-07-22: openrouter_qwen3_coder_free RETIRADO — el provider smoke diario
    # lo marca dead (429 upstream persistente; última corrida 2026-07-17, único
    # failed de 14). Quemaba una llamada fallida por pasada del fallback de edit.
    # 2026-06-27: Nemotron-3-Ultra 550B gratis en OpenRouter. Prove-it en vivo: OK.
    Provider(
        name="openrouter_nemotron_ultra",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
        litellm_model="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        api_key_env="OPENROUTER_API_KEY",
        account_pool=["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"],
        rpm_limit=20,
        context_tokens=128000,
        roles=("chat",),
    ),
    # 2026-06-27: Hermes-3-405B gratis en OpenRouter (Nous Research). Prove-it en
    # vivo: OK, pero también rate-limited upstream con frecuencia (modelo popular).
    # roles=edit: antecedente Hermes 2 Pro ~90% precisión function-calling —
    # buena señal para seguir formato estructurado (investigación harness survey).
    # 2026-07-08: openrouter_hermes_405b (hermes-3-llama-3.1-405b:free) RETIRADO
    # — NotFound verificado en vivo (OpenRouter eliminó el tier gratis; coherente
    # con el prove-it 2026-07-02: Hermes 4 solo paid). Ver hermes-4-70b L2 abajo.
    # 2026-07-02: Hermes 4 (70B/405B) prove-it en vivo — SIN tier gratis en
    # ningún proveedor confirmado (OpenRouter solo tiene paid; nuestro tier
    # NIM no lo lista en /v1/models real). hermes-4-70b funciona en vivo con
    # la cuenta actual ($0.13/$0.40 por M tokens) — L2 pago, mismo patrón que
    # el resto del catálogo NIM pago. hermes-4-405b es real pero la cuenta
    # OpenRouter actual no tiene crédito suficiente para el max_tokens por
    # defecto (65536) — NO se añade hasta decisión explícita de financiarlo.
    Provider(
        name="openrouter_hermes4_70b",
        level=InferenceLevel.L2,
        base_url="https://openrouter.ai/api/v1",
        model_id="nousresearch/hermes-4-70b",
        litellm_model="openrouter/nousresearch/hermes-4-70b",
        api_key_env="OPENROUTER_API_KEY",
        account_pool=["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"],
        rpm_limit=20,
        context_tokens=131072,
        roles=("chat", "edit"),
    ),
    Provider(
        name="together_free",
        level=InferenceLevel.L1,
        base_url="https://api.together.xyz/v1",
        model_id="meta-llama/Llama-3-8b-chat-hf",
        litellm_model="together_ai/meta-llama/Llama-3-8b-chat-hf",
        api_key_env="TOGETHERAI_API_KEY",
        rpm_limit=10,
        context_tokens=8192,
    ),
    Provider(
        name="gemini_free",
        level=InferenceLevel.L0,  # no sigue formato SEARCH/REPLACE; excluido de workers de código
        base_url="https://generativelanguage.googleapis.com",
        model_id="gemini-2.5-flash",
        litellm_model="gemini/gemini-2.5-flash",
        api_key_env="GEMINI_API_KEY",
        rpm_limit=15,
        context_tokens=1000000,
    ),
    # 2026-06-28: nvidia_qwen3_coder RETIRADO — prove-it en vivo confirma
    # HTTP 410 Gone: "The model 'qwen/qwen3-coder-480b-a35b-instruct' has
    # reached its end of life on 2026-06-11T00:00:00Z". Estaba MUERTO desde
    # antes de que lo "verificáramos" el 2026-06-26 (esa verificación no hizo
    # una llamada real, o el modelo murió justo después). El acceso vía OpenRouter
    # (openrouter_qwen3_coder_free) también cayó — retirado 2026-07-22 (429
    # upstream persistente): Qwen3-Coder-480B ya no tiene acceso vivo en la cadena.
    #
    # L2 — NVIDIA NIM (meta/llama-3.3-70b-instruct, pool 2 cuentas). Prove-it 2026-06-22:
    # en este tier responden modelos 70B; 405b/deepseek/nemotron dan 404/410. Aporta
    # 2º proveedor + account_pool/fallback, no un modelo mayor que groq-70b.
    Provider(
        name="nvidia_llama_large",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="meta/llama-3.3-70b-instruct",
        litellm_model="nvidia_nim/meta/llama-3.3-70b-instruct",
        api_key_env="NVIDIA_API_KEY",
        free_tier=False,
        rpm_limit=30,
        context_tokens=128000,
        account_pool=[f"NVIDIA_API_KEY_{i}" if i > 1 else "NVIDIA_API_KEY" for i in range(1, 9)],
        roles=("apply",),  # mecánico, contraparte de pago de groq_llama_70b
    ),
    # L2 — NVIDIA NIM modelos frontier extra. Mismo account_pool → fallback
    # entre modelos y entre cuentas. mistral-large-2-instruct da 404 en este
    # tier (descartado). nvidia_kimi (moonshotai/kimi-k2.6) RETIRADO
    # 2026-07-10: 404 "Function not found for account" en las 2 cuentas del
    # pool, dos días seguidos de smoke — sigue listado en /v1/models pero el
    # tier no lo sirve. Asiento CN re-mapeado a GLM (z-ai/glm-5.2, prove-it
    # en vivo 2026-07-10; el glm-5.1 anterior dio 410 Gone el 2026-06-28).
    Provider(
        name="nvidia_glm",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="z-ai/glm-5.2",
        litellm_model="nvidia_nim/z-ai/glm-5.2",
        api_key_env="NVIDIA_API_KEY",
        free_tier=False,
        rpm_limit=30,
        context_tokens=128000,
        account_pool=[f"NVIDIA_API_KEY_{i}" if i > 1 else "NVIDIA_API_KEY" for i in range(1, 9)],
        roles=("edit",),  # hereda el rol del asiento (métrica propia pendiente de medir)
    ),
    Provider(
        name="nvidia_mistral_large",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="mistralai/mistral-large-3-675b-instruct-2512",
        litellm_model="nvidia_nim/mistralai/mistral-large-3-675b-instruct-2512",
        api_key_env="NVIDIA_API_KEY",
        free_tier=False,
        rpm_limit=30,
        context_tokens=128000,
        account_pool=[f"NVIDIA_API_KEY_{i}" if i > 1 else "NVIDIA_API_KEY" for i in range(1, 9)],
        roles=("chat",),  # LiveCodeBench débil (0.465) vs Mistral Medium 3.5 — no "edit"
    ),
    # 2026-06-28: nvidia_glm RETIRADO — prove-it en vivo confirma HTTP 410 Gone
    # (mismo patrón que qwen3_coder). Reintentar si aparece GLM-5.2 en este tier.
    #
    # 2026-06-27: DeepSeek V4 (preview abr-2026) confirmado vivo en NIM en su
    # momento. 2026-06-28: prove-it en vivo AMBAS variantes CUELGAN (timeout
    # >45s, dos intentos, no es rate-limit transitorio de un segundo) —
    # comentadas hasta reverificar. codestral-22b-instruct-v0.1 (Mistral)
    # probado y descartado: 404 en este tier.
    #
    # 2026-06-27: Mistral Medium 3.5 (denso, 128B) — benchmark reportado mejor que
    # Mistral Large 3 (675B MoE) pese a ser mucho más pequeño. Prove-it en vivo: OK.
    Provider(
        name="nvidia_mistral_medium",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="mistralai/mistral-medium-3.5-128b",
        litellm_model="nvidia_nim/mistralai/mistral-medium-3.5-128b",
        api_key_env="NVIDIA_API_KEY",
        free_tier=False,
        rpm_limit=30,
        context_tokens=128000,
        account_pool=[f"NVIDIA_API_KEY_{i}" if i > 1 else "NVIDIA_API_KEY" for i in range(1, 9)],
        roles=("edit", "chat"),  # 77.6% SWE-bench Verified — mejor que Large 3 pese a ser más chico
    ),
    Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        # 2026-07-09: fix permanente aplicado (sudo systemctl edit ollama →
        # [Service] Environment="CUDA_VISIBLE_DEVICES=" → restart). GTX 960M
        # ahora corre sin CUDA. Último recurso: inagotable cuando gratis limitados.
        base_url="http://127.0.0.1:11434",
        # qwen2.5-coder:7b probado en vivo por Atlas; tools OK en Ollama.
        model_id="qwen2.5-coder:7b",
        litellm_model="ollama/qwen2.5-coder:7b",
        api_key_env=None,
        rpm_limit=999,
        context_tokens=8192,
    ),
]


class InferenceHub:
    """
    Router de inferencia con pool multi-cuenta, fallback chain y modo
    live/stub configurable. Backend real: LiteLLM (ADR-016).
    """

    def __init__(
        self,
        providers: list[Provider] | None = None,
        mode: str = "auto",
        merkle: "MerkleLogger" | None = None,
        transparency: "TransparencyGateway | None" = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if mode not in ("auto", "live", "stub"):
            raise ValueError(f"mode invalido: {mode}")
        self._providers = providers or DEFAULT_PROVIDERS
        self._mode = os.environ.get("ATLAS_INFERENCE_MODE", mode)
        self._calls: list[dict[str, Any]] = []
        self._rate_limited_until: dict[str, float] = {}
        self._merkle = merkle
        self._transparency = transparency
        self._sleep = sleep_fn

    @property
    def mode(self) -> str:
        return self._mode

    def _log_model_call(
        self,
        provider: Provider,
        request: InferenceRequest,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        if self._merkle is None:
            return
        payload: dict[str, Any] = {
            "provider": provider.name,
            "model": provider.model_id,
            "level": provider.level.value,
            "task_id": request.task_id,
            "mode": "live",
            "success": success,
        }
        if error is not None:
            payload["error"] = error
        self._merkle.log(
            action="model.called",
            agent="atlas.inference_hub",
            result="success" if success else "failed",
            risk_level="moderate",
            payload=payload,
            task_id=request.task_id,
        )

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        if self._transparency is not None:
            return self._infer_transparent(request)
        return self._infer_raw(request)

    def probe_provider(self, provider: Provider, request: InferenceRequest) -> InferenceResponse:
        """Llama a UN provider concreto, sin caminar la cadena de fallback ni
        tocar `_rate_limited_until` (uso: smoke de cadena — Fase 5, 2026-07-09).
        Wrapper público de `_call_provider` para no reencuadrar internals
        privados desde fuera del módulo."""
        return self._call_provider(provider, request)

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        """Lazo 4 — enruta por rol de tarea (edit/apply/chat), no solo por nivel.

        Soft-preference (patrón validado en Continue.dev/Cline/Cursor/Aider): los
        providers del nivel pedido etiquetados con *role* se REORDENAN al frente
        (no se descartan los demás) — así se prueban primero pero el fallback a
        L0 y al resto de providers del nivel sigue intacto si todos fallan. El
        rol es una preferencia de calidad, nunca un requisito duro que pueda
        hacer fallar la inferencia por falta de tag.
        """
        preferred = [
            p for p in self._providers
            if p.level == request.level and role in p.roles
        ]
        if not preferred:
            return self.infer(request)

        preferred_names = {p.name for p in preferred}
        rest = [p for p in self._providers if p.name not in preferred_names]

        saved = self._providers
        self._providers = preferred + rest
        try:
            return self.infer(request)
        finally:
            self._providers = saved

    def _infer_transparent(self, request: InferenceRequest) -> InferenceResponse:
        """Envuelve _infer_raw() con el protocolo de completitud (ADR-053).

        La firma bidireccional ocurre aquí automáticamente en background:
        subject_cosigner firma el request saliente, el gateway firma el Receipt
        de acuse, ambos InspectionRecords se commitean al log Merkle, y el
        APIResponse con STH + proofs se adjunta a la respuesta.
        """
        from atlas.transparency.gateway import TransparencyGateway  # evitar ciclo top-level

        captured: list[InferenceResponse] = []

        def call_fn(payload: bytes) -> bytes:
            # Desactivar temporalmente para evitar recursión
            saved_gw: TransparencyGateway | None = self._transparency
            self._transparency = None
            try:
                resp = self._infer_raw(request)
            finally:
                self._transparency = saved_gw
            captured.append(resp)
            return resp.text.encode("utf-8") if resp.success else b""

        payload = request.prompt.encode("utf-8")
        assert self._transparency is not None
        api_resp, _metrics = self._transparency.call(
            payload,
            call_fn,
            task_id=request.task_id or "",
        )

        resp = captured[0] if captured else InferenceResponse(
            text="", provider="none", model="none", level=request.level,
            latency_ms=0, success=False,
            error="gateway call produced no response",
            mode=self._mode,
        )
        resp.api_response = api_resp
        return resp

    @staticmethod
    def _mark_if_tools_unsupported(provider: Provider, error: str | None) -> None:
        """Autoaprendizaje 2026-07-08: si el proveedor rechaza tool-calling,
        se marca supports_tools=False en caliente — la siguiente petición con
        tools ya no quema una llamada ahí."""
        if error and "tool calling" in error.lower() and "not supported" in error.lower():
            provider.supports_tools = False

    def _earliest_ratelimit_wait(self) -> float | None:
        """Segundos hasta que expire el cooldown de rate-limit más próximo,
        o None si ningún proveedor está en cooldown."""
        now = time.time()
        pending = [t - now for t in self._rate_limited_until.values() if t > now]
        return min(pending) if pending else None

    def _infer_raw(self, request: InferenceRequest) -> InferenceResponse:
        """Camina la cadena; con ``wait_for_ratelimit`` re-camina tras esperar
        el cooldown si TODO falló y hay proveedores rate-limitados (incidente
        real 2026-07-08: 5 delegaciones de ToolCoder muertas por all_failed
        cuando esperar ~60s las habría salvado)."""
        walks = 3 if request.wait_for_ratelimit else 1
        resp = self._walk_chain(request)
        for _ in range(walks - 1):
            if resp.success:
                return resp
            wait = self._earliest_ratelimit_wait()
            if wait is None:
                break
            self._sleep(min(wait, 120.0) + 1.0)
            resp = self._walk_chain(request)

        # T5 (2026-07-23): CONTEXT_LENGTH ya no es terminal — condensa la
        # historia (recorte determinista, sin LLM) y reintenta la cadena UNA
        # vez antes de propagar el fallo. Sin nada que condensar (historia ya
        # mínima), no reintenta con una petición idéntica.
        if not resp.success and resp.error_kind == ErrorKind.CONTEXT_LENGTH.value:
            condensed = _condensed_request(request)
            if condensed is not None:
                resp = self._walk_chain(condensed)
        return resp

    def _walk_chain(self, request: InferenceRequest) -> InferenceResponse:
        needs_tools = bool(request.tools)
        candidates = [
            p for p in self._providers
            if p.level == request.level and p.status != ProviderStatus.DOWN
            and (not needs_tools or p.supports_tools)
        ]

        if not candidates and request.level == InferenceLevel.L1:
            candidates = [
                p for p in self._providers
                if p.level == InferenceLevel.L0
                and (not needs_tools or p.supports_tools)
            ]

        if not candidates:
            return InferenceResponse(
                text="", provider="none", model="none", level=request.level,
                latency_ms=0, success=False,
                error="Sin proveedores disponibles para el nivel solicitado.",
                mode=self._mode,
            )

        now = time.time()
        candidates = [
            p for p in candidates
            if self._rate_limited_until.get(p.name, 0.0) <= now
        ] or candidates

        # Orden estable por error_count: providers sanos mantienen el orden
        # declarado en DEFAULT_PROVIDERS, lo cual es curable por el operador
        # (poner primero los mas rapidos / preferidos). Si algun provider
        # acumula errores, baja en la cola.
        candidates.sort(key=lambda p: p.error_count)

        last_error: str | None = None
        last_resp: InferenceResponse | None = None
        for provider in candidates:
            result = self._call_provider(provider, request)
            last_resp = result
            if result.success:
                return result
            last_error = result.error
            self._mark_if_tools_unsupported(provider, result.error)
            if provider.status != ProviderStatus.RATELIMITED:
                provider.error_count += 1
                if provider.status == ProviderStatus.OK:
                    provider.status = ProviderStatus.DEGRADED

        if request.level == InferenceLevel.L1:
            l0_candidates = [
                p for p in self._providers
                if p.level == InferenceLevel.L0 and p.status != ProviderStatus.DOWN
                and (not needs_tools or p.supports_tools)
            ]
            if l0_candidates:
                l0_candidates = [
                    p for p in l0_candidates
                    if self._rate_limited_until.get(p.name, 0.0) <= now
                ] or l0_candidates
                l0_candidates.sort(key=lambda p: p.error_count)

                for provider in l0_candidates:
                    result = self._call_provider(provider, request)
                    last_resp = result
                    if result.success:
                        return result
                    last_error = result.error
                    self._mark_if_tools_unsupported(provider, result.error)
                    if provider.status != ProviderStatus.RATELIMITED:
                        provider.error_count += 1
                        if provider.status == ProviderStatus.OK:
                            provider.status = ProviderStatus.DEGRADED

        final_mode = last_resp.mode if last_resp is not None else self._mode
        return InferenceResponse(
            text="", provider="all_failed", model="none", level=request.level,
            latency_ms=0, success=False,
            error=last_error or "Todos los proveedores fallaron. Considera delegar a Hermes.",
            mode=final_mode,
            # T5.2/T5.3 T2 (2026-07-23): propaga la clasificación estructurada
            # del último fallo real (no la resetea a defaults) — el caller
            # sigue viendo por qué murió la cadena, no solo el string plano.
            error_kind=last_resp.error_kind if last_resp is not None else None,
            retry_after_s=last_resp.retry_after_s if last_resp is not None else None,
            retryable=last_resp.retryable if last_resp is not None else False,
        )

    def providers_status(self) -> list[dict[str, Any]]:
        now = time.time()
        return [
            {
                "name": p.name,
                "level": p.level.value,
                "model": p.model_id,
                "status": p.status.value,
                "error_count": p.error_count,
                "free_tier": p.free_tier,
                "last_used": p.last_used,
                "rate_limited_for_s": max(0, int(self._rate_limited_until.get(p.name, 0.0) - now)),
            }
            for p in self._providers
        ]

    def _resolve_live_for(self, provider: Provider) -> bool:
        if self._mode == "stub":
            return False
        if self._mode == "live":
            return True
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        if not _HAS_LITELLM:
            return False
        # L0 local (Ollama): sin API key, intenta real en auto mode.
        # Si Ollama no esta corriendo, _call_provider_real captura el error.
        if provider.api_key_env is None:
            return True
        if provider.account_pool:
            return any(os.environ.get(k) for k in provider.account_pool)
        return bool(os.environ.get(provider.api_key_env))

    def _call_provider(
        self, provider: Provider, request: InferenceRequest
    ) -> InferenceResponse:
        # Modo explicito stub: stub para todos.
        if self._mode == "stub":
            return self._call_provider_stub(provider, request)
        # Modo explicito live: real (fallara si no hay key).
        if self._mode == "live":
            return self._call_provider_real(provider, request)
        # Modo auto: usar real si hay key + litellm; en pytest cae a stub para
        # mantener la suite hermetica. Si NO hay key (y no estamos en pytest)
        # devolvemos un "skip" silencioso (success=False) para que infer()
        # pruebe el siguiente provider sin enmascarar nada como stub-exitoso.
        if self._resolve_live_for(provider):
            return self._call_provider_real(provider, request)
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return self._call_provider_stub(provider, request)
        return InferenceResponse(
            text="", provider=provider.name, model=provider.model_id,
            level=provider.level, latency_ms=0, success=False,
            error=f"sin key configurada ({provider.api_key_env})",
            mode="auto-skip",
        )

    def _call_provider_real(
        self, provider: Provider, request: InferenceRequest
    ) -> InferenceResponse:
        if not _HAS_LITELLM:
            return InferenceResponse(
                text="", provider=provider.name, model=provider.model_id,
                level=provider.level, latency_ms=0, success=False,
                error="litellm no instalado", mode="live",
            )

        start = time.perf_counter()
        provider.last_used = datetime.now(timezone.utc).isoformat()

        # ADR-031: si el caller provee `messages` (continuación multi-turno del
        # loop agéntico) se usan tal cual; si no, se construyen desde prompt/context.
        messages = _effective_messages(request)

        llm = _litellm_module()
        extra_kwargs: dict[str, Any] = {}
        if provider.api_key_env is None:
            extra_kwargs["api_base"] = provider.base_url
            extra_kwargs["api_key"] = "ollama"
        else:
            # Si hay account_pool, prueba cada clave en orden hasta encontrar una.
            # Sin pool (providers legacy), usa api_key_env directamente.
            key: str | None = None
            if provider.account_pool:
                for env_var in provider.account_pool:
                    key = os.environ.get(env_var)
                    if key:
                        break
            else:
                key = os.environ.get(provider.api_key_env)
            if key:
                extra_kwargs["api_key"] = key
        if request.tools:
            extra_kwargs["tools"] = request.tools
            extra_kwargs["tool_choice"] = request.tool_choice
        if provider.extra_body:
            extra_kwargs["extra_body"] = provider.extra_body

        timeout_s = request.timeout_s if request.timeout_s is not None else INFER_REQUEST_TIMEOUT_S
        max_retries = request.max_retries if request.max_retries is not None else INFER_MAX_RETRIES

        completion: Any = None
        last_exc: BaseException | None = None
        for attempt in range(max_retries + 1):
            try:
                completion = llm.completion(
                    model=provider.litellm_model,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    timeout=timeout_s,
                    **extra_kwargs,
                )
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 — clasificamos abajo
                last_exc = exc
                if _is_transient(exc) and attempt < max_retries:
                    backoff = INFER_RETRY_BASE_S * (2 ** attempt)
                    self._sleep(backoff + random.uniform(0.0, INFER_RETRY_BASE_S))
                    continue
                break

        if last_exc is not None:
            duration_ms = int((time.perf_counter() - start) * 1000)
            err_name = type(last_exc).__name__
            err_msg = f"{err_name}: {last_exc}"
            provider_error = classify_provider_error(last_exc)
            self._classify_error(provider, last_exc)
            self._log_model_call(provider, request, success=False, error=err_msg)
            self._calls.append({
                "provider": provider.name,
                "task_id": request.task_id,
                "level": request.level.value,
                "success": False,
                "error": err_msg,
                "mode": "live",
            })
            return InferenceResponse(
                text="", provider=provider.name, model=provider.model_id,
                level=provider.level, latency_ms=duration_ms, success=False,
                error=err_msg, mode="live",
                error_kind=provider_error.kind.value,
                retry_after_s=provider_error.retry_after_s,
                retryable=provider_error.retryable,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        text = _extract_text(completion)
        tokens = _extract_tokens(completion)
        tool_calls = _extract_tool_calls(completion)
        finish_reason = _extract_finish_reason(completion)

        if provider.status in (ProviderStatus.DEGRADED, ProviderStatus.RATELIMITED):
            provider.status = ProviderStatus.OK
            provider.error_count = 0

        self._log_model_call(provider, request, success=True)
        self._calls.append({
            "provider": provider.name,
            "task_id": request.task_id,
            "level": request.level.value,
            "success": True,
            "mode": "live",
        })
        return InferenceResponse(
            text=text, provider=provider.name, model=provider.model_id,
            level=provider.level, latency_ms=duration_ms, success=True,
            tokens_used=tokens, mode="live",
            tool_calls=tool_calls, finish_reason=finish_reason,
        )

    def _call_provider_stub(
        self, provider: Provider, request: InferenceRequest
    ) -> InferenceResponse:
        start = time.perf_counter()
        provider.last_used = datetime.now(timezone.utc).isoformat()

        stub_text = (
            f"[InferenceHub stub — proveedor: {provider.name}, "
            f"modelo: {provider.model_id}]\n"
            f"Prompt recibido ({len(request.prompt)} chars)."
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._calls.append({
            "provider": provider.name,
            "task_id": request.task_id,
            "level": request.level.value,
            "success": True,
            "mode": "stub",
        })
        return InferenceResponse(
            text=stub_text, provider=provider.name, model=provider.model_id,
            level=provider.level, latency_ms=duration_ms, success=True,
            tokens_used=len(request.prompt.split()), mode="stub",
        )

    def _classify_error(self, provider: Provider, exc: BaseException) -> None:
        # T5.2/T5.3 T2 (2026-07-23): delega en la fuente única de verdad
        # (provider_errors.classify_provider_error) en vez de substring-matching
        # propio. AUTH/NOT_FOUND son permanentes (key muerta / modelo
        # decomisionado) -> DOWN, no se re-queman. RATE_LIMIT honra
        # retry_after_s del proveedor (Retry-After / x-ratelimit-reset-*) si
        # vino en la excepción; si no, cae al cooldown fijo previo
        # (comportamiento por defecto intacto).
        pe = classify_provider_error(exc)
        if pe.kind == ErrorKind.RATE_LIMIT:
            provider.status = ProviderStatus.RATELIMITED
            cooldown = pe.retry_after_s if pe.retry_after_s is not None else RATE_LIMIT_COOLDOWN_S
            self._rate_limited_until[provider.name] = time.time() + cooldown
        elif pe.kind in (ErrorKind.AUTH, ErrorKind.NOT_FOUND):
            provider.status = ProviderStatus.DOWN
            provider.error_count += 1
        else:
            provider.error_count += 1
            if provider.status == ProviderStatus.OK:
                provider.status = ProviderStatus.DEGRADED


def _extract_text(completion: Any) -> str:
    try:
        return str(completion.choices[0].message.content or "")
    except (AttributeError, IndexError, KeyError):
        return ""


def _extract_tokens(completion: Any) -> int:
    try:
        return int(completion.usage.total_tokens)
    except (AttributeError, KeyError, TypeError):
        return 0


def _extract_tool_calls(completion: Any) -> list[dict[str, Any]]:
    """Normaliza los tool_calls del completion a {id, name, arguments(str)}.

    LiteLLM expone los tool_calls en el formato OpenAI
    (choices[0].message.tool_calls[*].function.{name,arguments}). Devuelve []
    si el modelo no pidió herramientas (respuesta final).
    """
    try:
        raw = completion.choices[0].message.tool_calls or []
    except (AttributeError, IndexError, KeyError):
        return []
    out: list[dict[str, Any]] = []
    for i, tc in enumerate(raw):
        try:
            out.append({
                "id": getattr(tc, "id", None) or f"call_{i}",
                "name": tc.function.name,
                "arguments": tc.function.arguments or "{}",
            })
        except AttributeError:
            continue
    return out


def _extract_finish_reason(completion: Any) -> str:
    try:
        return str(completion.choices[0].finish_reason or "")
    except (AttributeError, IndexError, KeyError):
        return ""
