"""Detector de deriva mapa-del-ecosistema↔disco (spec B+C §5, MAXIMUS
Cycle 13). "Deriva: pieza en disco sin fila en el mapa → hallazgo del
radar" se traduce, determinista y barato (mismo principio que
``sanitation_audit.py``: nunca LLM, nunca red), a: ¿todo ADR real
(``docs/decisions/adr/``) tiene su número citado en algún sitio de
``docs/design/atlas_ecosystem_map.md``?

Los ADR ya son el mecanismo establecido de este repo para "decisión de
arquitectura/capacidad" — y el propio mapa ya cita ADRs como columna
Evidence/Authority en casi todas sus filas (individualmente, `ADR-072`, o
por rango inclusivo, `ADR-024..040`, cuando varios ADRs contiguos comparten
una única fila "SELLADO"). Reusar esa convención evita inventar un
vocabulario de "pieza" nuevo que el mapa no habla."""

from __future__ import annotations

import re
from pathlib import Path

_ADR_FILENAME_RE = re.compile(r"^adr_(\d+)([a-z]?)_", re.IGNORECASE)
# El sufijo-letra opcional solo cuenta si NO sigue otra minúscula: distingue
# "ADR-013b" (letra pegada al número, sufijo real) de una cita por nombre de
# fichero completo "adr_072_supply_chain...md" (donde "s" de "supply" no es
# un sufijo, es el arranque del slug — `(?![a-z])` lo rechaza como sufijo y
# el match cae correctamente a "solo número").
_CITATION_RE = re.compile(
    r"\bADR[-_](\d+)([a-z]?)(?![a-z])(?:\.\.(\d+)([a-z]?)(?![a-z]))?", re.IGNORECASE
)


def _adr_entries(repo_root: Path) -> list[tuple[int, str, str]]:
    """(número, sufijo_letra, nombre_fichero) por cada ADR real en disco."""
    adr_dir = repo_root / "docs" / "decisions" / "adr"
    if not adr_dir.is_dir():
        return []
    entries: list[tuple[int, str, str]] = []
    for path in sorted(adr_dir.glob("*.md")):
        match = _ADR_FILENAME_RE.match(path.name)
        if match:
            entries.append((int(match.group(1)), match.group(2).lower(), path.name))
    return entries


def _cited_keys(map_text: str) -> set[tuple[int, str]]:
    """Claves (número, sufijo) cubiertas por el texto del mapa — expande
    citas de rango (``ADR-024..040``) a cada número intermedio, sin
    sufijo (los rangos de este repo no mezclan ADRs con letra)."""
    cited: set[tuple[int, str]] = set()
    for match in _CITATION_RE.finditer(map_text):
        start = int(match.group(1))
        start_suffix = match.group(2).lower()
        end_raw = match.group(3)
        if end_raw is None:
            cited.add((start, start_suffix))
            continue
        end = int(end_raw)
        for number in range(min(start, end), max(start, end) + 1):
            cited.add((number, ""))
    return cited


def ecosystem_map_drift(repo_root: Path) -> list[str]:
    """ADRs reales cuyo número no aparece citado (individual o por rango)
    en ninguna parte del mapa — "pieza sin fila" (spec B+C §5). Fail-honesto:
    si el mapa no existe, cada ADR real cuenta como drift (nada que lo cite);
    nunca lanza."""
    map_path = repo_root / "docs" / "design" / "atlas_ecosystem_map.md"
    map_text = map_path.read_text(encoding="utf-8") if map_path.is_file() else ""
    cited = _cited_keys(map_text)

    findings: list[str] = []
    for number, suffix, filename in _adr_entries(repo_root):
        if (number, suffix) in cited:
            continue
        label = f"ADR-{number:03d}{suffix}"
        findings.append(f"{label} ({filename}) sin fila en docs/design/atlas_ecosystem_map.md")
    return findings
