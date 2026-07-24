"""Registro de rechazo permanente del Security Council Gate (ADR-077.3).

Mismo patrón append-only que `GatedLessonRecorder`
(`src/atlas/immunity/live_loop.py`): un rechazo nunca se sobrescribe ni se
borra. Un ``unblock`` es una línea NUEVA que anota la revocación -- HITL
explícito, nunca automático -- no una mutación de la original. Trazabilidad
completa de quién rechazó y quién desbloqueó, y cuándo.

Corta en corto los reintentos en bucle: un `action_hash` con rechazo vigente
no vuelve a correr el gate ni a re-escalar (hallazgo real de la auditoría
2026-07-24 -- `mcp_adopt` contra `ai.adeu/adeu` se reintentó 6 veces en un
día pese a estar ya marcado con hallazgo MAJOR de semgrep).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from atlas.core.decider.security_council_gate import SecurityReport


def is_rejected(action_hash: str, registry_path: Path) -> bool:
    """Recorre el log completo -- append-only, la última entrada sobre un
    hash (rejected o unblock) es la que decide el estado vigente."""
    if not registry_path.is_file():
        return False
    status: dict[str, bool] = {}
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        h = entry["action_hash"]
        status[h] = entry.get("event") != "unblock"
    return status.get(action_hash, False)


def record_rejection(
    action_hash: str,
    kind: str,
    descriptor: str,
    report: SecurityReport,
    registry_path: Path,
) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "event": "rejected",
        "action_hash": action_hash,
        "kind": kind,
        "descriptor": descriptor,
        "report": {
            "severity": report.severity.name,
            "checks_run": report.checks_run,
            "triggered_by": report.triggered_by,
            "recommended_action": report.recommended_action,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with registry_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def unblock(action_hash: str, registry_path: Path, *, reason: str, actor: str) -> bool:
    """Revoca un rechazo vigente. Devuelve ``False`` si no había nada que
    desbloquear -- evita registrar ruido para hashes que nunca se
    rechazaron (llamado solo desde el comando CLI, HITL explícito)."""
    if not is_rejected(action_hash, registry_path):
        return False
    entry = {
        "event": "unblock",
        "action_hash": action_hash,
        "reason": reason,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with registry_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True
