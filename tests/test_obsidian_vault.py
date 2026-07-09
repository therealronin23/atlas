"""Tests para parser obsidian_vault."""

from pathlib import Path
import pytest
from atlas.memory.obsidian_vault import parse_note, parse_vault


def test_parse_note_with_frontmatter_wikilinks_and_tags(tmp_path: Path):
    """Nota completa: frontmatter YAML + 2 wikilinks + alias + tags inline."""
    note = tmp_path / "test.md"
    note.write_text(
        """---
title: Test Note
tags: [important, review]
---

This is a [[link]] and [[another|with alias]].

Some text with #inline and #tags."""
    )

    result = parse_note(note)
    assert result["frontmatter"]["title"] == "Test Note"
    assert set(result["wikilinks"]) == {"link", "another"}
    assert set(result["tags"]) == {"important", "review", "inline", "tags"}
    assert "This is a [[link]]" in result["body"]


def test_parse_note_without_frontmatter(tmp_path: Path):
    """Nota sin frontmatter YAML."""
    note = tmp_path / "simple.md"
    note.write_text("Just [[a link]] and #sometag")

    result = parse_note(note)
    assert result["frontmatter"] == {}
    assert result["wikilinks"] == ["a link"]
    assert result["tags"] == ["sometag"]


def test_parse_vault_recursively(tmp_path: Path):
    """Vault con 3 notas en subdirectorio."""
    (tmp_path / "note1.md").write_text("---\n---\n[[note2]]")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "note2.md").write_text("Content with #tag")
    (tmp_path / "subdir" / "note3.md").write_text("---\ntitle: Deep\n---\nNo links")

    result = parse_vault(tmp_path)
    assert "note1.md" in result
    assert "subdir/note2.md" in result
    assert "subdir/note3.md" in result
    assert result["note1.md"]["wikilinks"] == ["note2"]
    assert result["subdir/note2.md"]["tags"] == ["tag"]


def test_parse_vault_ignores_obsidian_directory(tmp_path: Path):
    """Ignora notas dentro de .obsidian/."""
    (tmp_path / "public.md").write_text("visible")
    obsidian_dir = tmp_path / ".obsidian"
    obsidian_dir.mkdir()
    (obsidian_dir / "config.md").write_text("hidden")

    result = parse_vault(tmp_path)
    assert "public.md" in result
    assert not any(".obsidian" in path for path in result.keys())
