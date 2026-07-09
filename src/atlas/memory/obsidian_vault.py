"""Parser de vault Obsidian (markdown + wikilinks + frontmatter YAML) a estructuras verificables."""

import re
import yaml
from pathlib import Path
from typing import Any


def parse_note(path: Path) -> dict[str, Any]:
    """Parse nota Obsidian: extrae frontmatter YAML, wikilinks, tags, body.

    Args:
        path: Path a fichero .md

    Returns:
        {"frontmatter": dict, "wikilinks": [targets], "tags": [tags], "body": str}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    frontmatter: dict[str, Any] = {}
    body = raw

    if raw.startswith("---"):
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
        if match:
            fm_text, body = match.groups()
            try:
                frontmatter = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError:
                frontmatter = {}

    wikilinks: list[str] = []
    for match in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body):
        target = match.group(1).strip()
        if target and target not in wikilinks:
            wikilinks.append(target)

    tags: list[str] = []
    for match in re.finditer(r"#[\w\-]+", body):
        tag = match.group(0)[1:]
        if tag and tag not in tags:
            tags.append(tag)

    if isinstance(frontmatter, dict):
        fm_tags = frontmatter.get("tags", [])
        if isinstance(fm_tags, list):
            for tag in fm_tags:
                if tag and tag not in tags:
                    tags.append(tag)

    return {
        "frontmatter": frontmatter,
        "wikilinks": wikilinks,
        "tags": tags,
        "body": body,
    }


def parse_vault(root: Path) -> dict[str, dict[str, Any]]:
    """Parsea un vault Obsidian completo (recursivo, ignora .obsidian/).

    Args:
        root: Path a directorio raíz del vault

    Returns:
        {ruta_relativa: parse_note()} para todos los *.md
    """
    root = Path(root)
    result: dict[str, dict[str, Any]] = {}

    for md_file in root.rglob("*.md"):
        if ".obsidian" in md_file.parts:
            continue

        rel_path = str(md_file.relative_to(root))
        result[rel_path] = parse_note(md_file)

    return result
