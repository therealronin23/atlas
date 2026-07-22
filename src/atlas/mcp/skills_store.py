"""
Atlas Core — SkillStore: skills SERVIDOS por el tronco MCP, sin descarga (C paso 3).

Un skill = fichero markdown en un directorio. El tronco lo sirve como contenido
(tool `get_skill` + resource + prompt) → el modelo accede "de una", nada se instala
en `~/.claude/skills`. Fuente única (anti-deriva): el .md ES la fuente; no se copia.

Diseño: docs/design/mcp_sector_architecture_audit.md (mecanismo de skills).

2026-07-22 (ADR-073 A3.3 cerró el activador; este era el gap real que dejó
documentado: plugins activados sin consumidor): `plugins_active_root` opcional
descubre `<root>/<plugin_id>/skill/<contribution_id>.md` — exactamente el árbol
que `atlas.mcp.plugin_activator.PluginActivator` produce por symlink (fuente
única también aquí: se sirve el destino del link, nunca se copia). Namespace
`plugin:<plugin_id>/<contribution_id>` para que un plugin nunca pueda sombrear
ni confundirse con un skill nativo del mismo nombre.
"""

from __future__ import annotations

import re
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PLUGIN_PREFIX = "plugin:"


class SkillStore:
    """Sirve skills markdown de un directorio (`<name>.md`) + opcionalmente
    de plugins activados (`<plugins_active_root>/<plugin_id>/skill/*.md`)."""

    def __init__(self, root: Path, *, plugins_active_root: Path | None = None) -> None:
        self._root = Path(root)
        self._plugins_active_root = (
            Path(plugins_active_root) if plugins_active_root is not None else None
        )

    def list_skills(self) -> list[str]:
        names: list[str] = []
        if self._root.is_dir():
            names.extend(p.stem for p in self._root.glob("*.md"))
        names.extend(self._list_plugin_skills())
        return sorted(names)

    def get(self, name: str) -> str:
        if name.startswith(_PLUGIN_PREFIX):
            return self._get_plugin_skill(name)
        path = self._root / f"{name}.md"
        if not path.is_file():
            raise KeyError(f"skill desconocido: {name!r}")
        return path.read_text(encoding="utf-8")

    def _list_plugin_skills(self) -> list[str]:
        root = self._plugins_active_root
        if root is None or not root.is_dir():
            return []
        names: list[str] = []
        for plugin_dir in sorted(root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            skill_dir = plugin_dir / "skill"
            if not skill_dir.is_dir():
                continue
            for md in sorted(skill_dir.glob("*.md")):
                names.append(f"{_PLUGIN_PREFIX}{plugin_dir.name}/{md.stem}")
        return names

    def _get_plugin_skill(self, name: str) -> str:
        root = self._plugins_active_root
        rest = name[len(_PLUGIN_PREFIX):]
        plugin_id, _, contribution_id = rest.partition("/")
        if (
            root is None
            or not contribution_id
            or not _SAFE_SEGMENT.match(plugin_id)
            or not _SAFE_SEGMENT.match(contribution_id)
        ):
            raise KeyError(f"skill desconocido: {name!r}")
        # `path.is_file()` sigue symlinks (así aplica PluginActivator sus
        # contribuciones): esto NO es un rechazo de symlinks como en
        # plugin_admission — aquí el link ES el mecanismo esperado.
        path = root / plugin_id / "skill" / f"{contribution_id}.md"
        if not path.is_file():
            raise KeyError(f"skill desconocido: {name!r}")
        return path.read_text(encoding="utf-8")
