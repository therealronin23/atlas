"""Cumplimiento de la mesa de trabajo obligatoria (2026-07-23).

Diseño del operador: aviso no bloqueante si ``workbench://manifest`` no se ha
consultado recientemente, pero el hallazgo debe quedar registrado de forma
durable (nunca solo un recordatorio de un turno) para que un ciclo de
auditoría/coldupdate futuro lo revise y actúe. Fail-soft en todo: esto vive
dentro de un hook de prompts (``capability_route_hook.py``) que NUNCA debe
poder romperse por esto.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from atlas.mcp.router_telemetry import hash_prompt

DEFAULT_STALE_AFTER_SECONDS = 30 * 60  # 30 min: ventana razonable de "sesión de trabajo"


def _last_consultation_at(log_path: Path) -> datetime | None:
    if not log_path.is_file():
        return None
    try:
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return None
        last = json.loads(lines[-1])
        return datetime.fromisoformat(str(last["at"]))
    except Exception:  # noqa: BLE001 — log corrupto se trata como "sin consultar"
        return None


def is_stale(
    log_path: Path,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> bool:
    """True si no hay consulta registrada o si la última es más vieja que
    ``stale_after_seconds``. Un log ausente/corrupto cuenta como stale
    (fail-closed en la SEÑAL, no en el bloqueo -- ver check_and_record)."""
    last = _last_consultation_at(log_path)
    if last is None:
        return True
    reference = now if now is not None else datetime.now(timezone.utc)
    return (reference - last).total_seconds() > stale_after_seconds


def record_finding(findings_path: Path, *, prompt: str) -> None:
    """Deja constancia durable del hallazgo (JSONL append-only). El prompt
    JAMÁS se persiste en claro -- mismo contrato que router_telemetry.py."""
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "prompt_hash": hash_prompt(prompt),
            "finding": "workbench_not_consulted",
        },
        ensure_ascii=False,
    )
    with findings_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_and_record(
    *,
    consultation_log_path: Path,
    findings_path: Path,
    prompt: str,
    now: datetime | None = None,
) -> str | None:
    """Punto de entrada del hook. Fail-soft: cualquier excepción (I/O, permisos)
    se traga y devuelve None -- un fallo AQUÍ nunca debe bloquear un prompt.
    Devuelve un aviso corto si la mesa de trabajo está stale (y ya dejó el
    hallazgo registrado); None si está fresca o si algo falló al comprobarlo."""
    try:
        if not is_stale(consultation_log_path, now=now):
            return None
        record_finding(findings_path, prompt=prompt)
        return (
            "[mesa de trabajo] workbench://manifest no se ha consultado "
            "recientemente -- catálogo+lecciones+backlog+memoria en un único "
            "resource, léelo antes de trabajo sustancial. Aviso registrado "
            "(no bloqueante); un ciclo de auditoría/coldupdate revisará "
            "hallazgos repetidos."
        )
    except Exception:  # noqa: BLE001 — nunca romper el hook por esto
        return None
