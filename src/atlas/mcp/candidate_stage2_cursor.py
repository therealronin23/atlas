"""Cursor de estado para el vetting continuo (B.2, ADR-076).

``scripts/mcp_stage2_batch.py`` sobrescribe el reporte entero cada corrida y
siempre toma los primeros N elegibles -- en un tick continuo procesaría los
mismos N para siempre y perdería los resultados previos al sobrescribir. Este
módulo distingue tres estados y opera sobre el reporte fusionado como fuente
de verdad (no hace falta un cursor de posición aparte):

- ``completed``: ya vetado con éxito -- NUNCA se toca de nuevo.
- ``terminal``: falló por una razón que no cambia sin una acción externa
  (código no soportado, paquete inexistente, entry point ambiguo/ausente,
  rechazo HTTP deliberado del servidor) -- no se reprocesa.
- ``retryable``: falló por algo transitorio (5xx, timeout/conexión, redirect
  no seguido, crash no anticipado) -- se reintenta en ciclos siguientes.

Clasificación basada en los conteos reales de
``docs/design/mcp_catalog_stage2_report.jsonl`` (corrida 2026-07-24, 2100
filas, 904 completados). Fail-closed: una razón no catalogada cae a
``retryable`` -- "sigue intentando" nunca "descarta en silencio" (I6).
"""

from __future__ import annotations

import re
from typing import Any, Literal

Stage2Status = Literal["completed", "terminal", "retryable"]

_TERMINAL_HTTP_CODES = {"401", "403", "404", "405"}
_RETRYABLE_HTTP_CODES = {"0", "307", "308", "500", "502", "503", "530"}
_HTTP_REASON_RE = re.compile(r"^HTTP (\d+) del endpoint remoto")


def classify_stage2_status(row: dict[str, Any]) -> Stage2Status:
    """Clasifica una fila del reporte de stage2 (dict, forma real del JSONL)."""
    if row.get("completed") is True:
        return "completed"

    reason = str(row.get("reason", ""))

    m = _HTTP_REASON_RE.match(reason)
    if m:
        code = m.group(1)
        if code in _TERMINAL_HTTP_CODES:
            return "terminal"
        # HTTP 0 (conexión/timeout), 5xx, redirect no seguido, o cualquier
        # código HTTP no catalogado (429/410/421/201/...) -- fail-closed
        # hacia retryable, nunca se asume un rechazo permanente sin conocerlo.
        return "retryable"

    if "Resolución DNS fallida" in reason:
        return "terminal"
    if "registryType no soportado" in reason:
        return "terminal"
    if "no encontrado" in reason:
        return "terminal"
    if "no publicada" in reason:
        return "terminal"
    if reason.startswith("ambiguo:"):
        return "terminal"
    if "sin 'bin'" in reason or "sin [project.scripts]" in reason:
        return "terminal"

    # crash no anticipado y cualquier otra razón no catalogada (respuesta
    # no-JSON, JSON-RPC server error, respuesta vacía, ...): retryable.
    return "retryable"


def select_stage2_batch(
    triaged: list[dict[str, Any]],
    prior_report: dict[str, dict[str, Any]],
    *,
    limit_stdio: int,
    limit_http: int,
) -> tuple[list[str], list[str]]:
    """Selecciona el próximo lote por pista: nuevos (no en ``prior_report``)
    primero, luego ``retryable`` de ``prior_report``. Nunca ``terminal`` ni
    ``completed``. Ignora candidatos no elegibles de la etapa 1 (track
    ``unknown`` o inyección MAJOR+). Acota a los límites por pista."""

    def _select(track: str, limit: int) -> list[str]:
        eligible_names = [
            str(t["name"]) for t in triaged
            if t.get("track") == track and t.get("eligible")
        ]
        new_names = [n for n in eligible_names if n not in prior_report]
        retry_names = [
            n for n in eligible_names
            if n in prior_report and classify_stage2_status(prior_report[n]) == "retryable"
        ]
        return (new_names + retry_names)[:limit]

    return _select("stdio", limit_stdio), _select("http", limit_http)


def merge_stage2_report(
    prior: dict[str, dict[str, Any]], new_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """``new_rows`` pisa ``prior`` por nombre; el resto de ``prior`` se
    preserva intacto (nunca se pierden resultados previos por sobrescribir
    el reporte entero, a diferencia de ``mcp_stage2_batch.py`` de hoy)."""
    merged = dict(prior)
    for row in new_rows:
        merged[str(row["name"])] = row
    return merged
