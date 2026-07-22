"""T0.5b, paso 1 — inventario determinista del corpus (atlas_master_plan.md
§T0.5.b). Establece la línea base medible ("¿cuántos docs hay y dónde?")
ANTES de cualquier clasificación semántica contra el plan maestro, que es
juicio real y no cabe en un ciclo atómico. El bucket es una heurística por
convención de ruta, no una decisión de contenido: todo lo que no encaja en
una regla explícita se etiqueta ``sin_clasificar`` — nunca se inventa una
clasificación con falsa confianza (honestidad de capacidades)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["inventory_corpus"]

# Reglas en orden de especificidad: la primera que matchea gana. Documentado
# aquí porque es la única fuente de verdad de "qué significa cada bucket".
_PATH_RULES: tuple[tuple[str, str], ...] = (
    ("docs/design/atlas_master_plan.md", "alimenta_item"),
    ("docs/archive/", "historico"),
    ("docs/inbox/", "candidata"),
    ("docs/decisions/adr/", "alimenta_item"),
)


def _bucket_for(rel_path: str) -> str:
    for prefix_or_exact, bucket in _PATH_RULES:
        if prefix_or_exact.endswith("/"):
            if rel_path.startswith(prefix_or_exact):
                return bucket
        elif rel_path == prefix_or_exact:
            return bucket
    return "sin_clasificar"


def inventory_corpus(repo_root: Path) -> dict[str, Any]:
    """Recorre ``*.md`` en la raíz (no recursivo) y todo ``docs/**/*.md``.

    Determinista: mismo árbol -> mismo reporte (orden por ``path``, sin
    depender de orden de filesystem). No toca git ni red; solo lectura local.
    """
    root = repo_root.resolve()
    paths: list[Path] = sorted(root.glob("*.md"))
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        paths.extend(sorted(docs_dir.rglob("*.md")))

    docs: list[dict[str, Any]] = []
    for path in paths:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        docs.append(
            {
                "path": rel,
                "word_count": len(text.split()),
                "bucket": _bucket_for(rel),
            }
        )
    docs.sort(key=lambda d: str(d["path"]))

    buckets: dict[str, int] = {}
    for doc in docs:
        bucket = str(doc["bucket"])
        buckets[bucket] = buckets.get(bucket, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "total_docs": len(docs),
        "buckets": buckets,
        "docs": docs,
    }
