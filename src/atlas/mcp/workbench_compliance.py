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
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.mcp.router_telemetry import hash_prompt

DEFAULT_STALE_AFTER_SECONDS = 30 * 60  # 30 min: ventana razonable de "sesión de trabajo"

# 2026-07-25: cooldown de síntesis Gemini -- deliberadamente más grueso que
# DEFAULT_STALE_AFTER_SECONDS. Sirve de proxy de "sesión nueva" (evento) sin
# inventar un mecanismo de session-id: si la última consulta real (manual o
# sintetizada) tiene más de esto, se considera una sesión distinta y la
# síntesis es obligatoria; dentro de la ventana, staleness repetida es
# discrecional (solo el aviso de texto plano). Ver memoria
# trunk-plan-cooperation-design-2026-07-25.
DEFAULT_SYNTHESIS_COOLDOWN_SECONDS = 6 * 60 * 60


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


def summarize_compliance_findings(
    findings_path: Path,
    *,
    now: datetime | None = None,
    recent_window_seconds: int = 24 * 60 * 60,
    elevated_threshold: int = 20,
) -> dict[str, Any]:
    """Lee ``findings_path`` (JSONL append-only de ``record_finding``, ver
    ``maintenance_workbench_compliance_review_tick``) y decide un veredicto
    accionable sin borrar ni mutar nada: ese consumidor faltaba desde que se
    cableó el detector 2026-07-23 (mismo patrón "wire-before-claim" que el
    resto de la auditoría de esa fecha).

    Cuenta total y recientes (últimas ``recent_window_seconds``) por
    separado -- un volumen alto histórico no dice nada sobre AHORA; un
    volumen alto reciente sí es señal de "mira esto". ``verdict`` es
    "no_findings" (fichero ausente o vacío), "elevated" (recientes >=
    ``elevated_threshold``) o "normal". No pretende saber si son falsos
    positivos del detector o comportamiento real repetido -- eso es juicio
    humano; solo mide el volumen honestamente. Líneas individualmente
    corruptas se saltan (una línea rota no invalida el conteo entero, mismo
    principio que ``_last_consultation_at``)."""
    reference = now if now is not None else datetime.now(timezone.utc)
    if not findings_path.is_file():
        return {"total": 0, "recent": 0, "verdict": "no_findings", "window_seconds": recent_window_seconds}

    total = 0
    recent = 0
    for line in findings_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            at = datetime.fromisoformat(str(entry["at"]))
        except Exception:  # noqa: BLE001 — línea corrupta no invalida el resto
            continue
        total += 1
        if (reference - at).total_seconds() <= recent_window_seconds:
            recent += 1

    if total == 0:
        verdict = "no_findings"
    elif recent >= elevated_threshold:
        verdict = "elevated"
    else:
        verdict = "normal"
    return {"total": total, "recent": recent, "verdict": verdict, "window_seconds": recent_window_seconds}


def is_synthesis_due(
    log_path: Path,
    *,
    now: datetime | None = None,
    cooldown_seconds: int = DEFAULT_SYNTHESIS_COOLDOWN_SECONDS,
) -> bool:
    """True si nunca hubo consulta real registrada, o la última es más vieja
    que ``cooldown_seconds`` -- proxy de "sesión nueva" para decidir si la
    síntesis Gemini de primera-vez-por-sesión toca ahora."""
    last = _last_consultation_at(log_path)
    if last is None:
        return True
    reference = now if now is not None else datetime.now(timezone.utc)
    return (reference - last).total_seconds() > cooldown_seconds


def check_and_maybe_synthesize(
    *,
    consultation_log_path: Path,
    findings_path: Path,
    prompt: str,
    goal: str,
    synth_fn: Callable[[str], str | None] | None = None,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    synthesis_cooldown_seconds: int = DEFAULT_SYNTHESIS_COOLDOWN_SECONDS,
) -> str | None:
    """Punto de entrada del hook (diseño 2026-07-25). Igual que
    ``check_and_record`` si el manifest está fresco o si no hay ``synth_fn``.
    Si está stale Y es la primera vez de la sesión (``is_synthesis_due``),
    intenta un briefing real vía ``synth_fn(goal)`` -- si sale bien, cuenta
    como consulta real (resetea el reloj) y se devuelve. Si no toca síntesis,
    o ``synth_fn`` falla/devuelve vacío, cae al aviso de texto plano de
    siempre. Fail-soft total: nunca lanza."""
    try:
        if not is_stale(consultation_log_path, now=now, stale_after_seconds=stale_after_seconds):
            return None
        if synth_fn is not None and is_synthesis_due(
            consultation_log_path, now=now, cooldown_seconds=synthesis_cooldown_seconds
        ):
            briefing = synth_fn(goal)
            if briefing:
                from atlas.mcp.workbench_resources import record_consultation

                record_consultation(consultation_log_path)
                return "[mesa de trabajo -- síntesis Gemini]\n" + briefing
    except Exception:  # noqa: BLE001 — nunca romper el hook por esto
        pass
    return check_and_record(
        consultation_log_path=consultation_log_path,
        findings_path=findings_path,
        prompt=prompt,
        now=now,
    )
