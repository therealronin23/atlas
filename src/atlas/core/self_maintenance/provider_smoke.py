"""ProviderChainSmoke -- smoke diario de la cadena de proveedores (Fase 5, 2026-07-09).

Causa raíz del hueco (auditoría "cadena de proveedores podrida",
2026-07-08): 3 modelos muertos (decomisionados/renombrados upstream) se
descubrían por accidente, quemando una llamada real fallida en cada pasada
del fallback hasta que alguien los retiraba a mano de ``DEFAULT_PROVIDERS``.
No había nada que caminara la cadena PROACTIVAMENTE y dejara evidencia de
qué proveedor está vivo, muerto o rate-limited -- "falta smoke diario de
cadena" quedó anotado en memoria sin cablear.

Una llamada mínima (``max_tokens`` bajo, prompt corto) por proveedor, vía
``InferenceHub.probe_provider`` (bypasea la cadena de fallback: cada
proveedor se prueba en aislamiento, un muerto no oculta a los demás). Sin
API key configurada -> ``skipped`` (no es un fallo real, nada que reportar).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceHub,
    InferenceRequest,
    Provider,
)

_PROBE_PROMPT = "ping"
_PROBE_MAX_TOKENS = 8
# 2026-07-22: política de probe acotada. El smoke heredaba la política de
# producción del hub (120s × 3 intentos, Timeout=transitorio) y un proveedor
# colgado retuvo la pasada 18 minutos medidos (nvidia_mistral_medium,
# latency_ms=1087936). Un probe responde "¿vive?" en segundos; si un proveedor
# necesita >30s para un ping de 8 tokens, ese dato ES el resultado del smoke.
#
# 2026-07-23: el cap de 30s de arriba NO se estaba cumpliendo de verdad —
# `timeout_s` pasado a litellm.completion no acotaba la duración real
# (probado en vivo: timeout=10 tardó ~34s, timeout=30 tardó ~92s, factor
# ~3x consistente; causa exacta en litellm/openai-sdk no aislada). Arreglado
# en `InferenceHub._call_provider_real` con un wrapper de hilo que fuerza el
# corte real — este cap de 30s ahora sí es el límite duro. Con esto, si
# `nvidia_glm`/`nvidia_mistral_medium` siguen apareciendo "dead" en el smoke
# diario durante varios días seguidos (no solo un run), ESO sí es evidencia
# suficiente para retirarlos de DEFAULT_PROVIDERS — un timeout puntual no lo
# es (ver WORK_LEDGER.md, auditoría 2026-07-23).
_PROBE_TIMEOUT_S = 30.0
_PROBE_MAX_RETRIES = 0


@dataclass
class ProviderSmokeResult:
    provider_name: str
    level: str
    outcome: str  # "ok" | "failed" | "skipped"
    latency_ms: int
    error: str | None
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "level": self.level,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "checked_at": self.checked_at,
        }


class ProviderChainSmoke:
    """Camina DEFAULT_PROVIDERS (o una lista inyectada) con una llamada
    mínima por proveedor, en aislamiento -- un proveedor muerto no bloquea
    ni enmascara a los demás (mismo principio fail-closed-por-unidad que
    PanoramaScout)."""

    def __init__(
        self, *, hub: InferenceHub, providers: list[Provider] | None = None
    ) -> None:
        self._hub = hub
        self._providers = providers if providers is not None else list(DEFAULT_PROVIDERS)

    def run(self) -> list[ProviderSmokeResult]:
        results: list[ProviderSmokeResult] = []
        for provider in self._providers:
            request = InferenceRequest(
                prompt=_PROBE_PROMPT,
                level=provider.level,
                max_tokens=_PROBE_MAX_TOKENS,
                task_id="provider_smoke.probe",
                timeout_s=_PROBE_TIMEOUT_S,
                max_retries=_PROBE_MAX_RETRIES,
            )
            response = self._hub.probe_provider(provider, request)
            if response.mode == "auto-skip":
                outcome = "skipped"
            elif response.success:
                outcome = "ok"
            else:
                outcome = "failed"
            results.append(
                ProviderSmokeResult(
                    provider_name=provider.name,
                    level=provider.level.value if hasattr(provider.level, "value") else str(provider.level),
                    outcome=outcome,
                    latency_ms=response.latency_ms,
                    error=response.error,
                )
            )
        return results
