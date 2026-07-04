"""
Tests de verificación — técnica #11 (Cline .clinerules): reglas condicionales
con frontmatter YAML (patrón glob 'applies_to') en vez de todo-o-nada.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.conditional_rules import load_conditional_rule


def test_rule_without_frontmatter_always_applies(tmp_path: Path):
    f = tmp_path / "rule.md"
    f.write_text("# regla sin condicion\nsiempre aplica\n")
    text = load_conditional_rule(f, context_files=["cualquier/cosa.py"])
    assert text is not None
    assert "siempre aplica" in text


def test_rule_with_matching_glob_applies(tmp_path: Path):
    f = tmp_path / "rule.md"
    f.write_text(
        "---\napplies_to: [\"*.py\"]\n---\n# regla python\nsolo para python\n"
    )
    text = load_conditional_rule(f, context_files=["src/foo.py"])
    assert text is not None
    assert "solo para python" in text
    assert "applies_to" not in text  # el frontmatter no se filtra al modelo


def test_rule_with_non_matching_glob_does_not_apply(tmp_path: Path):
    f = tmp_path / "rule.md"
    f.write_text(
        "---\napplies_to: [\"*.rs\"]\n---\n# regla rust\nsolo para rust\n"
    )
    text = load_conditional_rule(f, context_files=["src/foo.py"])
    assert text is None


def test_missing_file_returns_none(tmp_path: Path):
    assert load_conditional_rule(tmp_path / "no_existe.md", context_files=["a.py"]) is None
