"""T0.5b, paso 2 — clasificación semántica del corpus contra el plan maestro
(``atlas_master_plan.md`` §5, tramos T0-T6).

Paso 1 (``corpus_inventory.py``, PRIME Cycle 4) estableció la línea base por
convención de ruta: 602/701 docs (86%) quedaron honestamente ``sin_clasificar``
porque una regla de ruta no es juicio de contenido. Este módulo resuelve esa
brecha por similitud coseno de embeddings contra cada sección del plan, con
el umbral 0.5 YA MEDIDO en una sesión previa (2026-07-17: positivos>=0.533,
ruido<=0.449; ver también ``atlas.mcp.memory_server._SEMANTIC_MATCH_THRESHOLD``,
mismo valor, mismo origen) — no se re-deriva aquí, se reusa.

Límite honesto heredado de esa misma medición: un doc LARGO entero puntúa por
debajo del umbral (~0.45) incluso cuando SÍ alimenta un tramo — un solo vector
para miles de palabras diluye la señal. El chunking que arreglaría esto es su
propio trabajo de infraestructura (fuera de esta loncha, deliberadamente): un
doc largo relevante puede quedar honestamente ``sin_clasificar`` en vez de una
clasificación con confianza inventada.

Solo reclasifica lo que ``inventory_corpus`` dejó en ``sin_clasificar`` —
nunca reinterpreta un bucket ya asignado por regla de ruta (paso 1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from atlas.immunity.lesson_recaller import _cosine_similarity

__all__ = [
    "SEMANTIC_MATCH_THRESHOLD",
    "classify_corpus_semantically",
    "extract_plan_sections",
]

# Medido 2026-07-17 (ola bootstrap); mismo valor que memory_server, no una
# nueva calibración — reusar, no reinventar.
SEMANTIC_MATCH_THRESHOLD = 0.5

_SECTION5 = re.compile(
    r"^## 5\. El plan por tramos.*?(?=^## \d|\Z)", re.MULTILINE | re.DOTALL
)
_TRAMO_HEADER = re.compile(r"^### (T\d+) — (.+)$", re.MULTILINE)


class _Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def extract_plan_sections(master_plan_text: str) -> dict[str, str]:
    """``{"T0": "<título>\\n<cuerpo>", ...}`` desde ``## 5. El plan por
    tramos`` hasta el siguiente encabezado ``## N.``. Vacío si la sección no
    existe (fail-honesto: nunca inventa tramos)."""
    section5 = _SECTION5.search(master_plan_text)
    body = section5.group(0) if section5 else master_plan_text
    matches = list(_TRAMO_HEADER.finditer(body))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        tramo, title = match.group(1), match.group(2)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[tramo] = f"{title}\n{body[start:end]}".strip()
    return sections


def classify_corpus_semantically(
    inventory: dict[str, Any],
    *,
    repo_root: Path,
    embedder: _Embedder,
    threshold: float = SEMANTIC_MATCH_THRESHOLD,
) -> dict[str, Any]:
    """Reclasifica los docs ``sin_clasificar`` de ``inventory`` (salida de
    ``inventory_corpus``) contra las secciones del plan maestro. Devuelve una
    COPIA del inventario: los docs que superan ``threshold`` ganan bucket
    ``alimenta_item_semantico`` + ``semantic_match``/``semantic_score``; el
    resto queda ``sin_clasificar`` con el score igualmente registrado —
    nunca una confianza inventada por omisión."""
    plan_path = repo_root / "docs" / "design" / "atlas_master_plan.md"
    sections = extract_plan_sections(plan_path.read_text(encoding="utf-8"))
    section_vectors = {tramo: embedder.embed(text) for tramo, text in sections.items()}

    docs = [dict(doc) for doc in inventory["docs"]]
    buckets = dict(inventory["buckets"])

    for doc in docs:
        if doc["bucket"] != "sin_clasificar":
            continue
        path = repo_root / str(doc["path"])
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue

        vec = embedder.embed(text)
        best_tramo, best_score = "", 0.0
        for tramo, section_vec in section_vectors.items():
            score = _cosine_similarity(vec, section_vec)
            if score > best_score:
                best_tramo, best_score = tramo, score

        doc["semantic_score"] = round(best_score, 4)
        doc["semantic_match"] = best_tramo or None
        if best_score >= threshold:
            buckets["sin_clasificar"] = buckets.get("sin_clasificar", 0) - 1
            buckets["alimenta_item_semantico"] = buckets.get("alimenta_item_semantico", 0) + 1
            doc["bucket"] = "alimenta_item_semantico"

    return {**inventory, "docs": docs, "buckets": buckets, "semantic_threshold": threshold}
