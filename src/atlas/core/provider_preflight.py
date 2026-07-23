"""Atlas Core -- provider_preflight: go/no-go barato antes de una tanda
pesada de iteraciones.

Plan `docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md` (T5).
Pedido original del operador: "antes de iterar a lo loco diga si el
proveedor está disponible". Un loop pesado (SelfBuildRunner, digestión
masiva, Cónclave) llama ``provider_preflight(level)`` ANTES de lanzar N
iteraciones caras y aborta rápido y barato si no hay ningún proveedor vivo
de ese nivel -- en vez de descubrirlo a mitad de una tanda cara.

Dos capas, de más barata a más cara, corta en la primera que decide:

- **Capa 0 (cero red)**: lee ``workspace/self_build/provider_smoke_state.json``
  ya escrito por ``ProviderChainSmoke`` (T5.1, ver
  ``self_maintenance/provider_smoke.py``). Si hay >=1 proveedor del nivel
  pedido con ``outcome="ok"`` y ``checked_at`` <24h de antigüedad -> ``ok=True``
  SIN llamar a ``discover_available_models`` en absoluto.
- **Capa 1 (red barata, cero tokens)**: solo si Capa 0 no resuelve (estado
  ausente, corrupto, viejo, o sin ningún ``ok`` fresco del nivel) o si se
  pide ``require_live_probe=True`` -- usa ``discover_available_models`` como
  ping (``GET /v1/models``): outcome="ok" -> vivo, "auth_failed"/"unreachable"/
  "skipped" -> muerto. Nunca hace una llamada de inferencia real.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from atlas.core.inference_hub import DEFAULT_PROVIDERS, InferenceLevel, Provider
from atlas.core.provider_discovery import DiscoveryResult, discover_available_models

_SMOKE_STATE_FILENAME = "provider_smoke_state.json"
# Misma ventana de frescura que motiva el smoke diario (T5.1): un resultado
# "ok" de hace más de 24h ya no es evidencia suficiente de que el proveedor
# siga vivo AHORA.
_FRESHNESS_WINDOW = timedelta(hours=24)


@dataclass
class PreflightVerdict:
    ok: bool
    level: str
    reason: str
    live_providers: list[str] = field(default_factory=list)
    dead_providers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "level": self.level,
            "reason": self.reason,
            "live_providers": self.live_providers,
            "dead_providers": self.dead_providers,
        }


def _smoke_state_path(root: Path) -> Path:
    return root / "workspace" / "self_build" / _SMOKE_STATE_FILENAME


def _parse_checked_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fresh_ok_providers_from_smoke(
    root: Path, provider_names: set[str]
) -> set[str] | None:
    """Capa 0, cero red. Devuelve el subconjunto de ``provider_names`` con
    ``outcome="ok"`` y ``checked_at`` <24h en el último smoke persistido, o
    ``None`` si el fichero de estado no existe, es ilegible, o no trae nada
    usable -- en cuyo caso Capa 1 decide. Nunca lanza (mismo principio
    fail-honesto que ``reality._provider_smoke_state``)."""
    path = _smoke_state_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    results = raw.get("last_results")
    if not isinstance(results, list):
        return None

    now = datetime.now(timezone.utc)
    fresh_ok: set[str] = set()
    for entry in results:
        if not isinstance(entry, dict):
            continue
        name = entry.get("provider_name")
        if name not in provider_names:
            continue
        if entry.get("outcome") != "ok":
            continue
        checked_at = _parse_checked_at(entry.get("checked_at"))
        if checked_at is None:
            continue
        if now - checked_at < _FRESHNESS_WINDOW:
            fresh_ok.add(name)
    return fresh_ok


def provider_preflight(
    level: InferenceLevel,
    *,
    root: Path,
    providers: list[Provider] | None = None,
    require_live_probe: bool = False,
    discover: Callable[[Provider], DiscoveryResult] = discover_available_models,
) -> PreflightVerdict:
    """Go/no-go barato para un nivel de la cadena ANTES de lanzar una tanda
    de iteraciones caras. Ver docstring del módulo para el detalle de las 2
    capas."""
    level_value = level.value if hasattr(level, "value") else str(level)
    all_providers = providers if providers is not None else list(DEFAULT_PROVIDERS)
    level_providers = [p for p in all_providers if p.level == level]

    if not level_providers:
        return PreflightVerdict(
            ok=False,
            level=level_value,
            reason=f"no hay proveedores configurados para el nivel {level_value}",
        )

    provider_names = {p.name for p in level_providers}

    if not require_live_probe:
        fresh_ok = _fresh_ok_providers_from_smoke(root, provider_names)
        if fresh_ok:
            dead_from_smoke = sorted(provider_names - fresh_ok)
            return PreflightVerdict(
                ok=True,
                level=level_value,
                reason=(
                    f"{len(fresh_ok)} proveedor(es) del nivel {level_value} con "
                    "smoke <24h en outcome=ok (Capa 0, sin tocar red)"
                ),
                live_providers=sorted(fresh_ok),
                dead_providers=dead_from_smoke,
            )

    # Capa 1: ping barato vía discover_available_models -- GET /v1/models,
    # cero llamadas de inferencia real.
    live: list[str] = []
    dead: list[str] = []
    for provider in level_providers:
        result = discover(provider)
        if result.outcome == "ok":
            live.append(provider.name)
        else:
            dead.append(provider.name)

    if live:
        return PreflightVerdict(
            ok=True,
            level=level_value,
            reason=(
                f"{len(live)} proveedor(es) del nivel {level_value} responden "
                "/v1/models (Capa 1, ping en vivo sin inferencia)"
            ),
            live_providers=sorted(live),
            dead_providers=sorted(dead),
        )

    return PreflightVerdict(
        ok=False,
        level=level_value,
        reason=(
            f"ningún proveedor vivo del nivel {level_value} tras smoke en disco "
            "+ ping en vivo (Capa 0 + Capa 1)"
        ),
        live_providers=[],
        dead_providers=sorted(dead),
    )
