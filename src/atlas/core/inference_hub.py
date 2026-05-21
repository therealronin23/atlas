"""
Atlas Core — InferenceHub v0.1
Router de modelos con pool multi-cuenta y fallback chain.
Concepto del chat de Gemini: "free tiers oportunistas + rotacion entre proveedores".

Jerarquia de inferencia (del blueprint completo v1.1):
  L-det  → Herramienta determinista, sin LLM
  L0     → Modelo local (Ollama: Qwen-2.5, Phi-4)
  L1     → API gratuita (Groq free, OpenRouter free, Together AI, Gemini free)
  L2     → Frontier (solo cuando L0+L1 fallan o tarea lo requiere)

v0.1: InferenceHub es un stub con routing rule-based.
      Los proveedores reales se configuran en Gate C.
      LiteLLM como capa de abstraccion (ADR resuelto en chat de Gemini).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class InferenceLevel(str, Enum):
    L_DET = "L-det"   # Sin LLM
    L0    = "L0"      # Local (Ollama)
    L1    = "L1"      # Free API (Groq, OpenRouter, Together, Gemini)
    L2    = "L2"      # Frontier (fallback extremo)


class ProviderStatus(str, Enum):
    OK       = "ok"
    DEGRADED = "degraded"
    DOWN     = "down"
    RATELIMITED = "rate_limited"


@dataclass
class Provider:
    name: str
    level: InferenceLevel
    base_url: str
    model_id: str
    free_tier: bool = True
    rpm_limit: int  = 30          # requests per minute
    context_tokens: int = 8192
    account_pool: list[str] = field(default_factory=list)  # multi-cuenta
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


# Pool de proveedores free tier (configuracion v0.1)
DEFAULT_PROVIDERS: list[Provider] = [
    Provider(
        name="groq_llama",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="llama-3.3-70b-versatile",
        free_tier=True,
        rpm_limit=30,
        context_tokens=32768,
    ),
    Provider(
        name="groq_qwen",
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="qwen-qwq-32b",
        free_tier=True,
        rpm_limit=30,
        context_tokens=32768,
    ),
    Provider(
        name="openrouter_free",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="meta-llama/llama-3.1-8b-instruct:free",
        free_tier=True,
        rpm_limit=20,
        context_tokens=8192,
    ),
    Provider(
        name="together_free",
        level=InferenceLevel.L1,
        base_url="https://api.together.xyz/v1",
        model_id="meta-llama/Llama-3-8b-chat-hf",
        free_tier=True,
        rpm_limit=10,
        context_tokens=8192,
    ),
    Provider(
        name="gemini_free",
        level=InferenceLevel.L1,
        base_url="https://generativelanguage.googleapis.com",
        model_id="gemini-1.5-flash",
        free_tier=True,
        rpm_limit=15,
        context_tokens=1000000,
    ),
    Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        base_url="http://localhost:11434",
        model_id="qwen2.5-coder:7b",
        free_tier=True,
        rpm_limit=999,
        context_tokens=8192,
    ),
]


class InferenceHub:
    """
    Router de inferencia con pool multi-cuenta y fallback chain.
    v0.1: Stub — retorna respuesta simulada.
    Gate C: Implementacion real con LiteLLM como backend.
    """

    def __init__(self, providers: list[Provider] | None = None) -> None:
        self._providers = providers or DEFAULT_PROVIDERS
        self._calls: list[dict] = []

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        """
        Enruta la peticion al proveedor optimo segun nivel, disponibilidad
        y latencia. Fallback automatico si el proveedor falla.
        """
        candidates = [p for p in self._providers if p.level == request.level and p.status != ProviderStatus.DOWN]

        if not candidates and request.level == InferenceLevel.L1:
            # Fallback a L0 local si L1 falla
            candidates = [p for p in self._providers if p.level == InferenceLevel.L0]

        if not candidates:
            return InferenceResponse(
                text="",
                provider="none",
                model="none",
                level=request.level,
                latency_ms=0,
                success=False,
                error="Sin proveedores disponibles para el nivel solicitado.",
            )

        # Intentar en orden (prioridad: menos errores, mayor contexto disponible)
        candidates.sort(key=lambda p: (p.error_count, -p.context_tokens))
        for provider in candidates:
            result = self._call_provider_stub(provider, request)
            if result.success:
                return result
            provider.error_count += 1
            provider.status = ProviderStatus.DEGRADED

        return InferenceResponse(
            text="",
            provider="all_failed",
            model="none",
            level=request.level,
            latency_ms=0,
            success=False,
            error="Todos los proveedores fallaron. Considera delegar a Hermes.",
        )

    def providers_status(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "level": p.level.value,
                "model": p.model_id,
                "status": p.status.value,
                "error_count": p.error_count,
                "free_tier": p.free_tier,
            }
            for p in self._providers
        ]

    def _call_provider_stub(
        self, provider: Provider, request: InferenceRequest
    ) -> InferenceResponse:
        """
        Stub de llamada a proveedor.
        Gate C: sustituir por litellm.completion(model=provider.model_id, ...)
        """
        start = time.perf_counter()
        provider.last_used = datetime.now(timezone.utc).isoformat()

        # Simular respuesta
        stub_text = (
            f"[InferenceHub stub — proveedor: {provider.name}, "
            f"modelo: {provider.model_id}]\n"
            f"Prompt recibido ({len(request.prompt)} chars). "
            f"Implementacion real con LiteLLM en Gate C."
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._calls.append({
            "provider": provider.name,
            "task_id": request.task_id,
            "level": request.level.value,
            "success": True,
        })

        return InferenceResponse(
            text=stub_text,
            provider=provider.name,
            model=provider.model_id,
            level=request.level,
            latency_ms=duration_ms,
            success=True,
            tokens_used=len(request.prompt.split()),
        )
