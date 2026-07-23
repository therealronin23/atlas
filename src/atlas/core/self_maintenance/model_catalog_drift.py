"""ModelCatalogDrift -- deriva entre `model_id` configurado y catálogo servido.

Plan `docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md` (T4).
`DEFAULT_PROVIDERS` en `inference_hub.py` fija `model_id` a mano; este módulo
cruza ese id configurado contra lo que `discover_available_models` (T3,
`provider_discovery.py`) confirma que el proveedor sirve AHORA -- cero
llamadas de inferencia. Predice el mismo fallo que ya mordió a la cadena
(qwen3-coder 410 Gone, nvidia_kimi 404 "Function not found", deepseek
decomisionado, ver comentarios en DEFAULT_PROVIDERS) ANTES de gastarlo en una
llamada real.

No sustituye al smoke (`provider_smoke.py`): un proveedor puede *listar* un
modelo que su tier no sirve realmente (caso NIM), así que "present" aquí
significa "el catálogo lo lista", no "la invocación funcionará". El drift
antecede y abarata al smoke, filtrando primero los muertos-por-catálogo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from atlas.core.inference_hub import DEFAULT_PROVIDERS, Provider
from atlas.core.provider_discovery import DiscoveryResult, discover_available_models

# Único sufijo cosmético verificado en DEFAULT_PROVIDERS real: OpenRouter marca
# el tier gratis con ':free' en el id (openrouter_nemotron, openrouter_nemotron_ultra).
# NO generalizar a "todo lo que sigue a ':'" -- Ollama usa ':' para el tag de
# versión real (ej. "qwen2.5-coder:7b"), que SÍ distingue un modelo de otro.
_COSMETIC_SUFFIX = ":free"


def _normalize_model_id(model_id: str) -> str:
    """Quita sufijos cosméticos antes de comparar -- evita falsos 'missing'
    quando la única diferencia entre configurado y servido es ':free'."""
    if model_id.endswith(_COSMETIC_SUFFIX):
        return model_id[: -len(_COSMETIC_SUFFIX)]
    return model_id


@dataclass
class CatalogDriftResult:
    provider_name: str
    configured_model: str
    present: bool | None  # True=servido, False=ausente (predice 404/410), None=no comprobable
    outcome: str  # "present" | "missing" | "skipped"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "configured_model": self.configured_model,
            "present": self.present,
            "outcome": self.outcome,
            "reason": self.reason,
        }


class ModelCatalogDrift:
    """Camina `providers` (o `DEFAULT_PROVIDERS`) y clasifica, por proveedor,
    si su `model_id` configurado sigue estando en el catálogo que el
    proveedor sirve ahora mismo -- un `CatalogDriftResult` por proveedor,
    nunca lanza (delega el manejo de fallos de red/auth a `discover`)."""

    def __init__(
        self,
        *,
        providers: Sequence[Provider] = DEFAULT_PROVIDERS,
        discover: Callable[[Provider], DiscoveryResult] = discover_available_models,
    ) -> None:
        self._providers = providers
        self._discover = discover

    def run(self) -> list[CatalogDriftResult]:
        results: list[CatalogDriftResult] = []
        for provider in self._providers:
            discovery = self._discover(provider)
            if discovery.outcome != "ok":
                reason = f"discovery outcome={discovery.outcome}"
                if discovery.reason:
                    reason = f"{reason}: {discovery.reason}"
                results.append(
                    CatalogDriftResult(
                        provider_name=provider.name,
                        configured_model=provider.model_id,
                        present=None,
                        outcome="skipped",
                        reason=reason,
                    )
                )
                continue

            configured_normalized = _normalize_model_id(provider.model_id)
            served_normalized = {_normalize_model_id(m) for m in discovery.model_ids}

            if configured_normalized in served_normalized:
                results.append(
                    CatalogDriftResult(
                        provider_name=provider.name,
                        configured_model=provider.model_id,
                        present=True,
                        outcome="present",
                        reason="",
                    )
                )
            else:
                results.append(
                    CatalogDriftResult(
                        provider_name=provider.name,
                        configured_model=provider.model_id,
                        present=False,
                        outcome="missing",
                        reason=(
                            f"{provider.model_id} no está en el catálogo servido "
                            f"por {provider.name} ahora mismo"
                        ),
                    )
                )
        return results
