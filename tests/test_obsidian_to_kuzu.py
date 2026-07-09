"""Tests — cargador Obsidian→Kuzu (eslabón de la fusión Graphify→Obsidian→Kuzu)."""

from pathlib import Path

import kuzu

from atlas.memory.obsidian_to_kuzu import load_vault_into_kuzu


def _mk_vault(root: Path) -> None:
    (root / "a.md").write_text(
        "---\ntitle: Nota A\ntype: concept\ncommunity: 3\ntags: [core]\n---\n"
        "Enlaza a [[b]] y a [[fantasma]].",
        encoding="utf-8",
    )
    (root / "sub").mkdir()
    (root / "sub" / "b.md").write_text("Vuelve a [[a]] con #tag", encoding="utf-8")


def test_load_vault_creates_notes_and_links(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _mk_vault(vault)
    db_path = tmp_path / "kuzu" / "test.kuzu"

    result = load_vault_into_kuzu(vault, db_path)

    assert result["notes"] == 2
    assert result["links"] == 2  # a→b y b→a
    assert result["unresolved"] == 1  # [[fantasma]] no existe

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:ObsidianNote) RETURN count(n)")
        assert r.get_next()[0] == 2
        r = conn.execute(
            "MATCH (a:ObsidianNote {path: 'a.md'})-[:LINKS_TO]->(b) RETURN b.path"
        )
        assert r.get_next()[0] == "sub/b.md"
        r = conn.execute("MATCH (n:ObsidianNote {path: 'a.md'}) RETURN n.title, n.tags")
        row = r.get_next()
        assert row[0] == "Nota A"
        assert "core" in row[1]
    finally:
        conn.close()
        db.close()


def test_load_vault_is_idempotent(tmp_path: Path):
    """Recargar el mismo vault no duplica notas ni links (MERGE, no CREATE)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _mk_vault(vault)
    db_path = tmp_path / "kuzu" / "test.kuzu"

    load_vault_into_kuzu(vault, db_path)
    result2 = load_vault_into_kuzu(vault, db_path)

    assert result2["notes"] == 2
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:ObsidianNote) RETURN count(n)")
        assert r.get_next()[0] == 2
        r = conn.execute("MATCH ()-[l:LINKS_TO]->() RETURN count(l)")
        assert r.get_next()[0] == 2
    finally:
        conn.close()
        db.close()


def test_empty_vault(tmp_path: Path):
    vault = tmp_path / "vacio"
    vault.mkdir()
    result = load_vault_into_kuzu(vault, tmp_path / "kuzu" / "e.kuzu")
    assert result == {"notes": 0, "links": 0, "unresolved": 0}
