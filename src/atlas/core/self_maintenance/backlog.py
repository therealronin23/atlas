"""Backlog loader for Atlas self-maintenance.

Parses docs/backlog.yaml and exposes BacklogItem dataclass + helpers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# deferred (2026-07-10): diferido por diseño hasta tener consumidor — vive en
# el YAML como documentación, pero pending()/next_runnable no lo sirven (la
# noche del 07-10 el lazo quemó intentos de 30 turnos + suite de 900s en un
# item cuyo propio why decía "sin consumidor todavía → diferido").
VALID_STATUSES = {"pending", "doing", "done", "deferred"}

# Backoff de cola: tras N fallos consecutivos, un item deja de acaparar el
# tick y se prueba el siguiente. Sin esto, `items[0]` fallando en bucle
# bloqueaba el lazo entero indefinidamente (absorb_harness_patterns consumió
# TODOS los ticks de la noche del 2026-07-08/09 mientras el resto esperaba).
MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True)
class BacklogItem:
    id: str
    title: str
    why: str
    targets: tuple[str, ...]
    acceptance: str
    priority: int
    status: str
    test_cmd: tuple[str, ...] | None = None


def load_backlog(path: Path) -> list[BacklogItem]:
    """Parse a backlog YAML file and return a list of BacklogItem.

    Raises ValueError if any item has an unknown status.
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    items: list[BacklogItem] = []
    for entry in raw.get("items", []):
        status: str = entry["status"]
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Item '{entry['id']}' has invalid status '{status}'. "
                f"Allowed: {sorted(VALID_STATUSES)}"
            )
        # test_cmd es opcional (backward-compat): items existentes sin el
        # campo siguen cargando igual, con test_cmd=None.
        raw_test_cmd = entry.get("test_cmd")
        items.append(
            BacklogItem(
                id=entry["id"],
                title=entry["title"],
                why=str(entry["why"]).strip(),
                targets=tuple(entry.get("targets", [])),
                acceptance=str(entry["acceptance"]).strip(),
                priority=int(entry["priority"]),
                status=status,
                test_cmd=tuple(raw_test_cmd) if raw_test_cmd else None,
            )
        )
    return items


def pending(items: list[BacklogItem]) -> list[BacklogItem]:
    """Return items with status 'pending', sorted by priority ascending."""
    return sorted(
        (item for item in items if item.status == "pending"),
        key=lambda i: i.priority,
    )


def load_queue_state(path: Path) -> dict[str, int]:
    """Contador de fallos consecutivos por item ({item_id: n}). Fichero
    ausente o corrupto = estado vacío (fail-open: nunca bloquea el tick)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in raw.items()}
    except (OSError, ValueError, AttributeError):
        return {}


def save_queue_state(path: Path, state: dict[str, int]) -> None:
    """Persiste el contador. Mejor esfuerzo: un fallo de disco no rompe el tick."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def next_runnable(
    items: list[BacklogItem],
    state: dict[str, int],
    *,
    open_proposal_item_ids: frozenset[str] = frozenset(),
) -> BacklogItem | None:
    """El primer pendiente (por prioridad) con menos de MAX_CONSECUTIVE_FAILURES
    fallos seguidos Y sin ya tener una propuesta abierta sin revisar
    (proposed/validated/approved en ColdUpdateManager) — si ya hay una
    esperando a un humano, gastar otro ciclo de ToolCoder solo genera un
    duplicado casi idéntico. Incidente real 2026-07-11: `run_item()` marca
    éxito (resetea el contador de fallos) en cuanto CREA una propuesta, no
    cuando el problema queda resuelto; sin esta exclusión, el mismo item
    volvía a tocarle turno al ciclo siguiente indefinidamente — 14
    propuestas de `project-graph-vault-wiring` en el ledger, ninguna
    revisada. Si TODOS los pendientes (tras excluir los bloqueados por
    propuesta abierta) están agotados por fallos, la cola degrada a
    round-robin lento como antes. Si lo único que bloquea es una propuesta
    abierta, no hay nada seguro que hacer este tick: devuelve None."""
    queue = pending(items)
    if not queue:
        return None
    candidates = [i for i in queue if i.id not in open_proposal_item_ids]
    if not candidates:
        return None
    runnable = [i for i in candidates if state.get(i.id, 0) < MAX_CONSECUTIVE_FAILURES]
    if runnable:
        return runnable[0]
    return min(candidates, key=lambda i: (state.get(i.id, 0), i.priority))


def record_outcome(state: dict[str, int], item_id: str, *, success: bool) -> dict[str, int]:
    """Actualiza el contador: éxito (o propuesta generada) lo resetea; fallo suma."""
    new = dict(state)
    if success:
        new.pop(item_id, None)
    else:
        new[item_id] = new.get(item_id, 0) + 1
    return new


def backlog_summary(items: list[BacklogItem]) -> dict[str, Any]:
    """Índice ligero del backlog: conteo por status + los 5 pendientes de mayor
    prioridad (id/title/priority, sin why/acceptance — eso es el detalle)."""
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    top_pending = [
        {"id": item.id, "title": item.title, "priority": item.priority}
        for item in pending(items)[:5]
    ]
    return {"total": len(items), "by_status": by_status, "top_pending": top_pending}
