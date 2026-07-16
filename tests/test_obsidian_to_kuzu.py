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


def test_cohesion_column_from_community_frontmatter(tmp_path: Path):
    """F3.4: la semántica de graphify (`cohesion:` en las notas _COMMUNITY_*)
    se persiste como columna DOUBLE; notas sin el campo quedan NULL."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_COMMUNITY_X.md").write_text(
        "---\ntype: community\ncohesion: 0.05\nmembers: 2\n---\n"
        "# X\n\n## Members\n- [[a]] - code\n- [[b]] - code\n",
        encoding="utf-8",
    )
    (vault / "a.md").write_text("---\ntitle: A\n---\ncuerpo", encoding="utf-8")
    (vault / "b.md").write_text("hola", encoding="utf-8")
    db_path = tmp_path / "kuzu" / "coh.kuzu"

    result = load_vault_into_kuzu(vault, db_path)
    assert result["notes"] == 3

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute(
            "MATCH (n:ObsidianNote) WHERE n.note_type = 'community' RETURN n.cohesion"
        )
        assert abs(r.get_next()[0] - 0.05) < 1e-9
        r = conn.execute("MATCH (n:ObsidianNote {path: 'a.md'}) RETURN n.cohesion")
        assert r.get_next()[0] is None
    finally:
        conn.close()
        db.close()


def test_cohesion_non_numeric_is_null_not_crash(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "c.md").write_text(
        "---\ntype: community\ncohesion: alta\n---\ncuerpo", encoding="utf-8"
    )
    db_path = tmp_path / "kuzu" / "bad.kuzu"

    result = load_vault_into_kuzu(vault, db_path)
    assert result["notes"] == 1

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:ObsidianNote {path: 'c.md'}) RETURN n.cohesion")
        assert r.get_next()[0] is None
    finally:
        conn.close()
        db.close()


def test_kuzu_alter_table_add_column_verdict(tmp_path: Path):
    """F3.4 — VEREDICTO pedido por el plan: ¿soporta Kuzu (pin >=0.11.3)
    `ALTER TABLE ... ADD <col> <tipo>`? Evidencia para la decisión [fable] de
    migrar la BD de producción con schema viejo (sin `cohesion`). PROHIBIDO
    tocar ~/atlas/memory/kuzu — esto corre solo sobre una BD scratch.

    También documenta el modo de fallo: el loader nuevo contra una BD con la
    tabla ObsidianNote VIEJA revienta en el SET de la columna ausente (el
    CREATE ... IF NOT EXISTS no añade columnas) — ALTER TABLE es el remedio.
    """
    db_path = tmp_path / "old-schema.kuzu"
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        # Schema VIEJO (el de producción hasta 2026-07-15): sin cohesion.
        conn.execute(
            "CREATE NODE TABLE ObsidianNote("
            "path STRING, title STRING, note_type STRING, community STRING, "
            "tags STRING[], ingested_at TIMESTAMP, PRIMARY KEY(path))"
        )
        conn.execute("CREATE (:ObsidianNote {path: 'vieja.md'})")
        # Veredicto: ALTER TABLE ADD funciona y las filas viejas quedan NULL.
        conn.execute("ALTER TABLE ObsidianNote ADD cohesion DOUBLE")
        r = conn.execute("MATCH (n:ObsidianNote) RETURN n.cohesion")
        assert r.get_next()[0] is None
    finally:
        conn.close()
        db.close()

    # Tras la migración, el loader nuevo carga sin error sobre esa BD.
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text(
        "---\ntype: community\ncohesion: 0.5\n---\ncuerpo", encoding="utf-8"
    )
    result = load_vault_into_kuzu(vault, db_path)
    assert result["notes"] == 1


def test_load_vault_spans_multiple_batches(tmp_path: Path):
    """Vault > _BATCH_SIZE (1000): ejercita el UNWIND en varios lotes, no solo uno."""
    vault = tmp_path / "vault"
    vault.mkdir()
    n = 1200
    for i in range(n):
        target = f"n{(i + 1) % n}"  # cada nota enlaza a la siguiente, en anillo
        (vault / f"n{i}.md").write_text(f"Enlaza a [[{target}]]", encoding="utf-8")
    db_path = tmp_path / "kuzu" / "big.kuzu"

    result = load_vault_into_kuzu(vault, db_path)

    assert result == {"notes": n, "links": n, "unresolved": 0}

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:ObsidianNote) RETURN count(n)")
        assert r.get_next()[0] == n
        r = conn.execute("MATCH ()-[l:LINKS_TO]->() RETURN count(l)")
        assert r.get_next()[0] == n
    finally:
        conn.close()
        db.close()
