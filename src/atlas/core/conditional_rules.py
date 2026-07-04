"""Atlas Core — Conditional Rules (técnica #11, patrón Cline .clinerules).

Reglas con frontmatter YAML opcional 'applies_to: [globs]' — más fino que
incluir un archivo todo-o-nada.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

__all__ = ["load_conditional_rule"]


def load_conditional_rule(path: Path, *, context_files: list[str]) -> str | None:
    """Lee path; si tiene frontmatter '---\\napplies_to: [...]\\n---' al
    inicio, solo devuelve el cuerpo (sin el frontmatter) si algún
    context_file matchea alguno de los globs. Sin frontmatter, siempre
    aplica. Archivo inexistente -> None."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    if not content.startswith("---\n"):
        return content
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return content
    frontmatter, body = parts[1], parts[2]
    globs: list[str] = []
    for line in frontmatter.splitlines():
        line = line.strip()
        if line.startswith("applies_to:"):
            raw = line.split(":", 1)[1].strip().strip("[]")
            globs = [g.strip().strip('"').strip("'") for g in raw.split(",") if g.strip()]
    if not globs:
        return body
    for cf in context_files:
        for pattern in globs:
            if fnmatch.fnmatch(Path(cf).name, pattern):
                return body
    return None
