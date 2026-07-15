"""Contrato del `.graphifyignore` de la raíz del repo.

GRAPHIFY_MAX_OUTPUT_TOKENS=4096 revienta con ficheros YAML/JSON de un solo
chunk >100KB: la extracción semántica devuelve "truncated at
max_completion_tokens" en vez de un grafo útil (56 truncados observados en
graphify-out/logs/pipeline.log contra docs/design/mcp_catalog_classified.yaml,
2026-07). `.graphifyignore` excluye esos ficheros del escaneo de graphify.

Este test se queda deliberadamente CIEGO a las internals de graphify: escribe
su propio parser mínimo estilo gitignore (líneas no-comentario, comparación
exacta o fnmatch) en vez de importar `graphify.detect._load_graphifyignore` /
`_is_ignored`. Verifica el contrato del fichero en disco, no la
implementación del paquete de terceros (que no debe tocarse ni importarse
como API privada).
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPHIFYIGNORE_PATH = REPO_ROOT / ".graphifyignore"

# Candidatos conocidos que revientan el presupuesto de tokens de un chunk
# single-file (find docs -type f \( -name "*.yaml" -o -name "*.json" \) -size +100k).
_KNOWN_OVERSIZED_DOCS = (
    "docs/design/mcp_catalog_classified.yaml",
    "docs/self_audit_latest.json",
    "docs/INDEX.yaml",
)


def _read_patterns(ignore_file: Path) -> list[str]:
    """Parser mínimo: líneas no vacías / no-comentario de un .graphifyignore."""
    patterns = []
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _is_covered(rel_path: str, patterns: list[str]) -> bool:
    """True si rel_path matchea un patrón por comparación exacta o fnmatch."""
    for raw_pattern in patterns:
        pattern = raw_pattern.strip("/")
        if pattern == rel_path:
            return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # patrón sin "/" matchea a cualquier profundidad, estilo gitignore
        if "/" not in pattern and fnmatch.fnmatch(Path(rel_path).name, pattern):
            return True
    return False


def test_graphifyignore_file_exists() -> None:
    assert GRAPHIFYIGNORE_PATH.is_file(), ".graphifyignore no existe en la raíz del repo"


def test_mcp_catalog_classified_is_covered() -> None:
    patterns = _read_patterns(GRAPHIFYIGNORE_PATH)
    assert _is_covered("docs/design/mcp_catalog_classified.yaml", patterns), (
        "docs/design/mcp_catalog_classified.yaml (195KB) no está cubierto por "
        ".graphifyignore — revienta GRAPHIFY_MAX_OUTPUT_TOKENS=4096"
    )


def test_other_known_oversized_docs_are_covered() -> None:
    patterns = _read_patterns(GRAPHIFYIGNORE_PATH)
    uncovered = [p for p in _KNOWN_OVERSIZED_DOCS if not _is_covered(p, patterns)]
    assert not uncovered, f"docs >100KB sin cubrir en .graphifyignore: {uncovered}"


def test_no_oversized_yaml_or_json_under_docs_is_uncovered() -> None:
    """Re-deriva los candidatos (find docs -size +100k) para no depender solo
    de la lista fija _KNOWN_OVERSIZED_DOCS: si aparece un doc nuevo >100KB sin
    cobertura, este test debe fallar en rojo antes de que vuelva a producir
    "truncated" en el pipeline."""
    patterns = _read_patterns(GRAPHIFYIGNORE_PATH)
    docs_dir = REPO_ROOT / "docs"
    oversized = [
        p
        for p in docs_dir.rglob("*")
        if p.is_file() and p.suffix in (".yaml", ".json") and p.stat().st_size > 100_000
    ]
    uncovered = [
        str(p.relative_to(REPO_ROOT))
        for p in oversized
        if not _is_covered(str(p.relative_to(REPO_ROOT)), patterns)
    ]
    assert not uncovered, f"docs >100KB sin cubrir en .graphifyignore: {uncovered}"
