"""
Atlas Core — SkillStore: skills SERVIDOS por el tronco MCP, sin descarga (C paso 3).

Un skill = fichero markdown en un directorio. El tronco lo sirve como contenido
(tool `get_skill` + resource + prompt) → el modelo accede "de una", nada se instala
en `~/.claude/skills`. Fuente única (anti-deriva): el .md ES la fuente; no se copia.

Diseño: docs/design/mcp_sector_architecture_audit.md (mecanismo de skills).
"""

from __future__ import annotations

from pathlib import Path


class SkillStore:
    """Sirve skills markdown de un directorio (`<name>.md`)."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def list_skills(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(p.stem for p in self._root.glob("*.md"))

    def get(self, name: str) -> str:
        path = self._root / f"{name}.md"
        if not path.is_file():
            raise KeyError(f"skill desconocido: {name!r}")
        return path.read_text(encoding="utf-8")
