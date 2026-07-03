#!/usr/bin/env python3
"""Siembra las 3 lecciones reales en el LessonStore del workspace.

Idempotente: si una lección con el mismo title ya existe, la omite.
Uso: python scripts/seed_lessons.py [--workspace /path/to/atlas]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TypedDict

# Añade src/ al path para importar atlas sin instalar en editable mode
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from atlas.core.lesson_store import LessonPromoter, LessonStore  # noqa: E402


class _LessonSpec(TypedDict):
    title: str
    avoid_pattern: str
    detection_heuristic: str
    tags: tuple[str, ...]


_LESSONS: list[_LessonSpec] = [
    dict(
        title="matcher",
        avoid_pattern=(
            "usar re.match en lugar de re.search cuando el patrón debe"
            " anclarse al inicio"
        ),
        detection_heuristic=(
            "código usa re.match() donde debería ser re.search() o re.fullmatch()"
        ),
        tags=("regex", "matcher"),
    ),
    dict(
        title="merkle-double-writer",
        avoid_pattern=(
            "abrir dos instancias de MerkleLogger sobre el mismo path"
            " simultáneamente"
        ),
        detection_heuristic=(
            "dos objetos MerkleLogger con el mismo path en el mismo proceso"
        ),
        tags=("merkle", "concurrency"),
    ),
    dict(
        title="recursive-suite",
        avoid_pattern=(
            "pytest descubre tests recursivamente desde src/ incluyendo archivos"
            " de fixtures — pasar --ignore=src a pytest o configurar testpaths"
            " en pyproject.toml"
        ),
        detection_heuristic=(
            "pytest corriendo desde raíz recoge archivos test_*.py dentro de src/"
        ),
        tags=("pytest", "discovery"),
    ),
]


def _seed(repo_root: Path) -> None:
    # 2026-07-03: unificado a <repo_root>/workspace/lessons — la MISMA
    # convención que AtlasCoder/ToolCoder (donde ya viven lecciones reales).
    # Antes usaba <workspace>/memory/lessons (p.ej. ~/.atlas/memory/lessons),
    # una ruta que ni siquiera existía — desconectada del resto de Atlas.
    store_path = repo_root / "workspace" / "lessons"
    store = LessonStore(store_path)
    promoter = LessonPromoter(store)

    existing_titles = {lesson.title for lesson in store.all()}

    seeded = 0
    skipped = 0

    for spec in _LESSONS:
        title = spec["title"]
        if title in existing_titles:
            print(f"  omitida (ya existe): {title!r}")
            skipped += 1
            continue

        result = promoter.ingest_external(
            title=title,
            detection_heuristic=spec["detection_heuristic"],
            avoid_pattern=spec["avoid_pattern"],
            source_refs=("repo:atlas-core",),
            corroborated=True,
            reason="lección real del repo",
            tags=tuple(spec["tags"]),
        )
        if result is not None:
            print(f"  sembrada: {title!r} (id={result.id})")
            seeded += 1
        else:
            # No debería ocurrir con corroborated=True, pero lo reportamos
            print(f"  RECHAZADA por el store: {title!r}", file=sys.stderr)

    print(f"\nResultado: {seeded} nueva(s), {skipped} ya existía(n).")


def main() -> None:
    # Default = la raíz de ESTE repo (donde AtlasCoder/ToolCoder ya escriben
    # lecciones reales en workspace/lessons), no ATLAS_HOME/~/.atlas — ver
    # nota de unificación en `_seed`.
    parser = argparse.ArgumentParser(
        description="Siembra 3 lecciones reales en el LessonStore de Atlas."
    )
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help=f"Raíz del repo de Atlas Core (default: {_REPO_ROOT})",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    print(f"Repo root: {repo_root}")

    _seed(repo_root)


if __name__ == "__main__":
    main()
