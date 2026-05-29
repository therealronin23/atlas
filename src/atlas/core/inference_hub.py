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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger

# Silenciar warnings cosmeticos de LiteLLM (bedrock/sagemaker pre-load, etc).
# Se debe hacer ANTES del import porque algunos warnings se emiten al cargar el modulo.
# No afecta a la chain Groq/OpenRouter/Together/Gemini que si usamos.
import logging as _logging  # noqa: E402

_logging.getLogger("LiteLLM").setLevel(_logging.ERROR)
_logging.getLogger("litellm").setLevel(_logging.ERROR)

try:
    import litellm
    _HAS_LITELLM = True
    try:
        litellm.suppress_debug_info = True
    except Exception:  # pragma: no cover
        pass
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore[assignment]
    _HAS_LITELLM = False


RATE_LIMIT_COOLDOWN_S = 60.0


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
    status: ProviderStatus = ProviderStatus.OK
    last_used: str | None = None
    error_count: int = 0


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


DEFAULT_PROVIDERS: list[Provider] = [
    Provider(
        name="groq_llama",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="llama-3.3-70b-versatile",
        litellm_model="groq/llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        rpm_limit=30,
        context_tokens=32768,
    ),
    Provider(
        name="groq_qwen",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="qwen/qwen3-32b",
        litellm_model="groq/qwen/qwen3-32b",
        api_key_env="GROQ_API_KEY",
        rpm_limit=30,
        context_tokens=32768,
    ),
    Provider(
        name="openrouter_nemotron",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="nvidia/nemotron-nano-12b-v2-vl:free",
        litellm_model="openrouter/nvidia/nemotron-nano-12b-v2-vl:free",
        api_key_env="OPENROUTER_API_KEY",
        rpm_limit=20,
        context_tokens=128000,
    ),
    Provider(
        name="openrouter_liquid",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="liquid/lfm-2.5-1.2b-instruct:free",
        litellm_model="openrouter/liquid/lfm-2.5-1.2b-instruct:free",
        api_key_env="OPENROUTER_API_KEY",
        rpm_limit=20,
        context_tokens=32768,
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
        level=InferenceLevel.L1,
        base_url="https://generativelanguage.googleapis.com",
        model_id="gemini-1.5-flash",
        litellm_model="gemini/gemini-1.5-flash",
        api_key_env="GEMINI_API_KEY",
        rpm_limit=15,
        context_tokens=1000000,
    ),
    Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        base_url="http://localhost:11434",
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
    ) -> None:
        if mode not in ("auto", "live", "stub"):
            raise ValueError(f"mode invalido: {mode}")
        self._providers = providers or DEFAULT_PROVIDERS
        self._mode = os.environ.get("ATLAS_INFERENCE_MODE", mode)
        self._calls: list[dict[str, Any]] = []
        self._rate_limited_until: dict[str, float] = {}
        self._merkle = merkle

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
        candidates = [
            p for p in self._providers
            if p.level == request.level and p.status != ProviderStatus.DOWN
        ]

        if not candidates and request.level == InferenceLevel.L1:
            candidates = [p for p in self._providers if p.level == InferenceLevel.L0]

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
            if provider.status != ProviderStatus.RATELIMITED:
                provider.error_count += 1
                if provider.status == ProviderStatus.OK:
                    provider.status = ProviderStatus.DEGRADED

        if request.level == InferenceLevel.L1:
            l0_candidates = [
                p for p in self._providers
                if p.level == InferenceLevel.L0 and p.status != ProviderStatus.DOWN
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
        if request.messages is not None:
            messages = list(request.messages)
        else:
            messages = [{"role": "user", "content": request.prompt}]
            if request.context:
                messages.insert(0, {"role": "system", "content": request.context})

        try:
            assert litellm is not None
            extra_kwargs: dict[str, Any] = {}
            if provider.api_key_env is None:
                extra_kwargs["api_base"] = provider.base_url
                extra_kwargs["api_key"] = "ollama"
            else:
                key = os.environ.get(provider.api_key_env)
                if key:
                    extra_kwargs["api_key"] = key
            if request.tools:
                extra_kwargs["tools"] = request.tools
                extra_kwargs["tool_choice"] = request.tool_choice
            completion = litellm.completion(
                model=provider.litellm_model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                **extra_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — clasificamos abajo
            duration_ms = int((time.perf_counter() - start) * 1000)
            err_name = type(exc).__name__
            err_msg = f"{err_name}: {exc}"
            self._classify_error(provider, exc)
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
        name = type(exc).__name__
        if "RateLimit" in name:
            provider.status = ProviderStatus.RATELIMITED
            self._rate_limited_until[provider.name] = time.time() + RATE_LIMIT_COOLDOWN_S
        elif "Authentication" in name or "PermissionDenied" in name:
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
