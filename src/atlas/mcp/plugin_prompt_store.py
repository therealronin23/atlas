"""
Atlas Core — PluginPromptStore: consumidor real de la contribución `prompt` de
plugins activados (t1-plugin-contribution-consumers, docs/backlog.yaml).

`PluginManifest v1` (ADR-073, docs/design/plugin_manifest_v1.md) admite 4 tipos de
contribución: skill, prompt, rule, command. Hasta este ítem solo `skill` tenía
consumidor real (`SkillStore` vía `plugins_active_root` — ver `skills_store.py`,
cerrado 2026-07-22 A3.3). `prompt`/`rule`/`command` se seguían aplicando
mecánicamente por `PluginActivator` (symlink bajo
`<active_root>/<plugin_id>/<kind>/*.md`) sin que nada los leyera.

Este módulo cierra el hueco para `prompt`: MISMO patrón exacto que `SkillStore`
(namespace `plugin:<plugin_id>/<contribution_id>`, sigue symlinks porque
`PluginActivator` aplica por symlink — fuente única, nunca copia bytes). A
diferencia de `SkillStore` no hay raíz "core"/nativa: hoy no existen prompts
bundleados en el repo, solo los que aporte un plugin activado — por eso el
constructor toma directamente `active_root` (sin el `root` posicional de
`SkillStore`).

`rule` y `command` quedan honestamente documentados en plugin_manifest_v1.md como
"aplicados mecánicamente, sin consumidor" — no se cablean en este ítem.

Consumidor real cableado en `trunk_server.py`: cada prompt de plugin activado se
registra como MCP `Prompt` nativo (mismo mecanismo que ya usa `SkillStore` para
sus skills — `Prompt.from_function` + `server.add_prompt`), descubrible vía
`list_prompts()`/`get_prompt()` por cualquier cliente MCP real.
"""

from __future__ import annotations

import re
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PLUGIN_PREFIX = "plugin:"


class PluginPromptStore:
    """Sirve contribuciones `prompt` de plugins activados
    (`<active_root>/<plugin_id>/prompt/*.md`)."""

    def __init__(self, active_root: Path) -> None:
        self._active_root = Path(active_root)

    def list_prompts(self) -> list[str]:
        root = self._active_root
        if not root.is_dir():
            return []
        names: list[str] = []
        for plugin_dir in sorted(root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            prompt_dir = plugin_dir / "prompt"
            if not prompt_dir.is_dir():
                continue
            for md in sorted(prompt_dir.glob("*.md")):
                names.append(f"{_PLUGIN_PREFIX}{plugin_dir.name}/{md.stem}")
        return sorted(names)

    def get(self, name: str) -> str:
        if not name.startswith(_PLUGIN_PREFIX):
            raise KeyError(f"prompt de plugin desconocido: {name!r}")
        rest = name[len(_PLUGIN_PREFIX):]
        plugin_id, _, contribution_id = rest.partition("/")
        if (
            not contribution_id
            or not _SAFE_SEGMENT.match(plugin_id)
            or not _SAFE_SEGMENT.match(contribution_id)
        ):
            raise KeyError(f"prompt de plugin desconocido: {name!r}")
        # `path.is_file()` sigue symlinks (así aplica PluginActivator sus
        # contribuciones): esto NO es un rechazo de symlinks como en
        # plugin_admission — aquí el link ES el mecanismo esperado.
        path = self._active_root / plugin_id / "prompt" / f"{contribution_id}.md"
        if not path.is_file():
            raise KeyError(f"prompt de plugin desconocido: {name!r}")
        return path.read_text(encoding="utf-8")
