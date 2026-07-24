"""Scanner específico de `mcp_adopt` para el Security Council Gate (ADR-077).

Hueco real encontrado en la implementación original: `default_scan_fn`
(regexes IOC/credencial genéricas) solo mira `action.descriptor`, que para
`mcp_adopt` es el nombre bare del candidato (ej. ``"ai.adeu/adeu"``) -- una
cadena de texto sin nada peligroso que un regex pueda encontrar. La
evidencia REAL (semgrep, ``worst_severity``) ya la calculó ADR-075 y vive en
``docs/design/mcp_catalog_stage2_report.jsonl``, pero el gate nunca la
consultaba.

Corrección explícita del operador (2026-07-24): el fix no puede anclarse a
un candidato conocido -- debe cubrir estructuralmente CUALQUIER candidato
futuro con evidencia real de riesgo. Este scanner consulta el reporte de
vetting real por nombre, no por patrón de texto.

Fail-closed en todos los casos ambiguos (I6, mismo principio que el resto
del pipeline de ADR-075/076): candidato sin fila en el reporte, vetting no
completado, o reporte inexistente -> nunca se asume limpio.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from atlas.core.decider.security_council_gate import ScanFinding

_DIRTY_SEVERITIES = {"MAJOR", "BLOCKING"}


def mcp_vetting_scan_fn(report_path: Path) -> Callable[[str], ScanFinding]:
    """Construye un `scan_fn` que consulta
    ``docs/design/mcp_catalog_stage2_report.jsonl`` (o el path inyectado) por
    nombre de candidato -- el `descriptor` de un `DecisionAction(kind=
    "mcp_adopt", ...)` es siempre el nombre del candidato (`cfg.name`,
    ver `Orchestrator.adopt_mcp_server`)."""

    def scan(descriptor: str) -> ScanFinding:
        if not report_path.is_file():
            return ScanFinding(
                clean=False,
                detail="sin reporte de vetting stage2 -- fail-closed, no vetado",
            )
        for line in report_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("name") != descriptor:
                continue

            if not row.get("completed", False):
                return ScanFinding(
                    clean=False,
                    detail=f"stage2 vetting no completado: {row.get('reason', '(sin razón)')}",
                )

            worst = row.get("worst_severity")
            if worst in _DIRTY_SEVERITIES:
                return ScanFinding(
                    clean=False,
                    detail=f"stage2 vetting real: worst_severity={worst}",
                )
            return ScanFinding(
                clean=True,
                detail="stage2 vetting real: completado, sin hallazgos MAJOR/BLOCKING",
            )

        return ScanFinding(
            clean=False,
            detail=f"candidato {descriptor!r} sin vetting stage2 registrado -- fail-closed",
        )

    return scan
