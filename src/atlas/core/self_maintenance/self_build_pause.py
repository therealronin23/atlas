"""Superficie de control operativo del self-build daemon (t1-daemon-control-surface).

Hoy el daemon de self-build corre dentro de ``atlas serve`` (proceso
foreground, resto: dashboard/API/MCP en el mismo proceso); la única forma de
detenerlo era matar el proceso entero. Este módulo añade un mecanismo de
pausa cooperativa vía fichero de estado (mismo patrón que
``SelfAuditRunner.stop()``/``stop_requested()`` en ``self_audit.py``, y que
``queue_state.json``/``provider_smoke_state.json`` en este mismo paquete):
``maintenance_self_build_tick`` (``maintenance_facade.py``) lo consulta al
principio de cada tick y, si está pausado, no toca el backlog ni gasta LLM —
un no-op auditado, sin afectar a ningún otro servicio de ``atlas serve``
(dashboard/API/MCP/otros ciclos del scheduler siguen corriendo intactos).

Fichero de estado en ``workspace/self_build/pause_state.json`` (mismo
directorio que ``queue_state.json``): su sola presencia es la señal de
pausa (fail-safe — un fichero corrupto o parcialmente escrito sigue
contando como "pausado", nunca al revés)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "PAUSED_LLM_TICKS",
    "is_paused",
    "llm_spend_paused",
    "pause",
    "pause_status",
    "resume",
]

#: Ticks de mantenimiento que GASTAN INFERENCIA y por tanto se detienen con la
#: pausa. El criterio es "consume LLM", no el nombre: un tick sin inferencia es
#: gratis y da observabilidad justo cuando el lazo está parado, así que sigue.
#:
#: Medido el 2026-08-09: con el lazo pausado desde el día 6, el daemon seguía
#: haciendo 128 `analyst_analyze` y 72 `panorama_scout_discover` en dos días —
#: deliberación cuyo consumidor no existía. `is_paused()` se consultaba en
#: EXACTAMENTE un sitio, el tick de self_build.
#:
#: Esta lista es documentación; quien la impide envejecer es
#: `tests/test_pause_stops_llm_spend.py`, que recorre los ticks reales y falla
#: si aparece uno con inferencia y sin guardia.
PAUSED_LLM_TICKS: tuple[str, ...] = (
    "maintenance_self_build_tick",
    "maintenance_scheduler",
    "maintenance_research_tick",
    "maintenance_knowledge_ingest_tick",
    "maintenance_cold_update_batcher",
)


def llm_spend_paused(repo_root: Path) -> bool:
    """¿Debe un tick que gasta inferencia abstenerse ahora mismo?

    Alias semántico de `is_paused` con nombre propio a propósito: el sitio de
    llamada dice POR QUÉ se detiene (gasta LLM y el lazo está parado), no sólo
    QUÉ bandera mira. La distinción importó al implementarlo — pausar el grafo
    o el watchdog habría sido un error, porque son gratis y son justo lo que se
    quiere ver mientras el lazo no corre.
    """
    return is_paused(repo_root)

_STATE_REL_PATH = Path("workspace") / "self_build" / "pause_state.json"


def _state_path(repo_root: Path) -> Path:
    return repo_root / _STATE_REL_PATH


def pause(repo_root: Path, *, reason: str = "") -> dict[str, Any]:
    """Activa la pausa: escribe el fichero de estado. Idempotente."""
    path = _state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "paused": True,
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def resume(repo_root: Path) -> None:
    """Desactiva la pausa: borra el fichero de estado. Idempotente (no
    lanza si ya no existe -- resume() sin pause() previo es un no-op)."""
    path = _state_path(repo_root)
    if path.exists():
        path.unlink()


def is_paused(repo_root: Path) -> bool:
    """Único punto de verdad que consulta el tick: la sola EXISTENCIA del
    fichero es la señal de pausa -- fail-safe ante un JSON corrupto (mejor
    pausado de más que perder la señal de pausa por un parseo roto)."""
    return _state_path(repo_root).exists()


def pause_status(repo_root: Path) -> dict[str, Any]:
    """Estado legible para ``atlas selfbuild status``/``atlas reality``.

    Fichero ausente -> ``{"paused": False}``. Fichero presente pero con JSON
    ilegible -> sigue reportando ``paused: True`` (misma razón fail-safe que
    ``is_paused``) con un motivo honesto en vez de reventar."""
    path = _state_path(repo_root)
    if not path.exists():
        return {"paused": False, "paused_at": None, "reason": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"paused": True, "paused_at": None, "reason": "pause_state.json unreadable"}
    if not isinstance(data, dict):
        return {"paused": True, "paused_at": None, "reason": "pause_state.json malformed"}
    return {
        "paused": True,
        "paused_at": data.get("paused_at"),
        "reason": data.get("reason") or None,
    }
