"""Tests de scripts/migrate_harness_memory.py (T0.2 del plan de sucesión).

Migra las memorias .md del harness (Claude Code, ~/.claude/projects/.../memory)
al sustrato de memoria propio (SqliteMemoryIndex + MemoryTrunk). Partición por
`metadata.type`: project/reference → factual, feedback → personal, user → NO
se migra (dato personal, queda en harness a propósito).

Spec: .superpowers/sdd/task-1-brief.md. Import por importlib (patrón de
tests/test_graphify_failure_guard.py:41-46) porque scripts/ no es un paquete.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from atlas.mcp.memory_trunk import MemoryTrunk
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_harness_memory.py"


def _mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migrate_harness_memory", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _test_index(db_path: Path) -> SqliteMemoryIndex:
    """Índice de test: mismo patrón que tests/test_mcp_memory_trunk.py:28 —
    StubEmbedder (hash, no semántico) para no depender de red/modelo ONNX."""
    return SqliteMemoryIndex(db_path, embedder=StubEmbedder(dim=64))


def _write_fixture_memories(mem: Path) -> None:
    (mem / "proj-x.md").write_text(
        "---\nname: proj-x\ndescription: hito del proyecto atlas\n"
        "metadata:\n  type: project\n---\n\ncuerpo proyecto\n",
        encoding="utf-8",
    )
    (mem / "feed-y.md").write_text(
        "---\nname: feed-y\ndescription: mania del operador sobre docs\n"
        "metadata:\n  type: feedback\n---\n\ncuerpo feedback\n",
        encoding="utf-8",
    )
    (mem / "user-z.md").write_text(
        "---\nname: user-z\ndescription: dato personal\n"
        "metadata:\n  type: user\n---\n\ncuerpo personal\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Step 1 (brief, verbatim): partición + idempotencia
# ---------------------------------------------------------------------------


def test_migrate_partitions_and_is_idempotent(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    index = _test_index(tmp_path / "db.sqlite")
    report = _mod().migrate(mem, index)
    assert report == {"migrated": 2, "skipped_user": 1, "errors": []}
    report2 = _mod().migrate(mem, index)
    assert report2["migrated"] == 2  # upsert, no duplica


def test_migrated_records_are_recallable_with_harness_prefixed_id(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    index = _test_index(tmp_path / "db.sqlite")
    trunk = MemoryTrunk(index)

    _mod().migrate(mem, index)

    hits = trunk.recall("hito del proyecto atlas")
    assert hits, "el record migrado debe ser recuperable por recall"
    assert hits[0].record_id == "harness:proj-x"


def test_user_type_is_never_written_to_the_index(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    index = _test_index(tmp_path / "db.sqlite")

    _mod().migrate(mem, index)

    assert index.text_of("harness:user-z") is None


def test_migrated_text_carries_the_migration_marker_and_full_body(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    index = _test_index(tmp_path / "db.sqlite")

    _mod().migrate(mem, index)

    text = index.text_of("harness:proj-x")
    assert text == "[migrado de memoria-harness 2026-07-16] hito del proyecto atlas\n\ncuerpo proyecto"


def test_project_and_feedback_map_to_the_right_memory_class(tmp_path: Path) -> None:
    """project/reference → factual (sin TTL); feedback → personal (con TTL,
    ver PERSONAL_TTL_S en memory_index.py) — confirma la partición por clase,
    no solo el conteo agregado."""
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    index = _test_index(tmp_path / "db.sqlite")

    _mod().migrate(mem, index)

    row = index._conn.execute(  # noqa: SLF001 — introspección de test, no API pública
        "SELECT memory_class FROM records WHERE id=?", ("harness:proj-x",)
    ).fetchone()
    assert row is not None and row[0] == "factual"
    row = index._conn.execute(  # noqa: SLF001
        "SELECT memory_class FROM records WHERE id=?", ("harness:feed-y",)
    ).fetchone()
    assert row is not None and row[0] == "personal"


def test_reference_type_is_migrated_as_factual(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "ref-a.md").write_text(
        "---\nname: ref-a\ndescription: nota de referencia externa\n"
        "metadata:\n  type: reference\n---\n\ncuerpo referencia\n",
        encoding="utf-8",
    )
    index = _test_index(tmp_path / "db.sqlite")

    report = _mod().migrate(mem, index)

    assert report == {"migrated": 1, "skipped_user": 0, "errors": []}
    assert index.text_of("harness:ref-a") is not None


def test_real_frontmatter_variants_are_parsed(tmp_path: Path) -> None:
    """El frontmatter real usa `metadata: ` con espacio final y descripciones
    entre comillas dobles (ver adopt-real-not-shell.md real) — el parser manual
    debe soportar ambas variantes, no solo la del fixture sintético del brief."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "quoted.md").write_text(
        '---\nname: quoted\ndescription: "Descripción entre comillas: con dos puntos dentro"\n'
        "metadata: \n  node_type: memory\n  type: feedback\n  originSessionId: abc-123\n---\n\ncuerpo\n",
        encoding="utf-8",
    )
    index = _test_index(tmp_path / "db.sqlite")

    report = _mod().migrate(mem, index)

    assert report["errors"] == []
    assert report["migrated"] == 1
    text = index.text_of("harness:quoted")
    assert text is not None
    assert "Descripción entre comillas: con dos puntos dentro" in text


def test_malformed_frontmatter_is_reported_as_error_not_a_crash(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "broken.md").write_text("no hay frontmatter aquí\n", encoding="utf-8")
    index = _test_index(tmp_path / "db.sqlite")

    report = _mod().migrate(mem, index)

    assert report["migrated"] == 0
    assert report["skipped_user"] == 0
    assert len(report["errors"]) == 1
    assert "broken.md" in report["errors"][0]


# ---------------------------------------------------------------------------
# --extra-doc: ingesta de doctrina (Task 3 del plan la necesita)
# ---------------------------------------------------------------------------


def test_migrate_extra_doc_ingests_full_text_as_doctrine(tmp_path: Path) -> None:
    doc = tmp_path / "doctrine-source.md"
    doc.write_text("# Doctrina\n\nTexto íntegro sin frontmatter que parsear.\n", encoding="utf-8")
    index = _test_index(tmp_path / "db.sqlite")

    record_id = _mod().migrate_extra_doc(doc, index)

    assert record_id == "doctrine:doctrine-source"
    assert index.text_of(record_id) == "# Doctrina\n\nTexto íntegro sin frontmatter que parsear.\n"


def test_migrate_extra_doc_is_idempotent(tmp_path: Path) -> None:
    doc = tmp_path / "doctrine-source.md"
    doc.write_text("v1 del doc\n", encoding="utf-8")
    index = _test_index(tmp_path / "db.sqlite")

    rid1 = _mod().migrate_extra_doc(doc, index)
    rid2 = _mod().migrate_extra_doc(doc, index)

    assert rid1 == rid2 == "doctrine:doctrine-source"
    row = index._conn.execute(  # noqa: SLF001
        "SELECT COUNT(*) FROM records WHERE id=?", (rid1,)
    ).fetchone()
    assert row is not None and row[0] == 1  # upsert, no duplica


# ---------------------------------------------------------------------------
# CLI: dry-run por defecto, --apply escribe de verdad
# ---------------------------------------------------------------------------


def test_cli_dry_run_does_not_touch_the_db(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    db = tmp_path / "would-be-created.db"

    rc = _mod().main(["--memory-dir", str(mem), "--db", str(db)])

    assert rc == 0
    assert not db.exists(), "sin --apply el CLI no debe escribir nada en disco"


def test_cli_apply_writes_to_the_given_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fixture_memories(mem)
    db = tmp_path / "real.db"
    # El CLI real abre el índice vía build_gated_index() -> default_embedder(),
    # que por defecto es FastEmbedEmbedder (ONNX real). Forzamos el stub barato
    # (hash, no semántico) para no depender del modelo cacheado en la máquina
    # que corre el test — mismo patrón que _test_index().
    monkeypatch.setenv("ATLAS_EMBEDDER", "stub")

    rc = _mod().main(["--memory-dir", str(mem), "--db", str(db), "--apply"])

    assert rc == 0
    assert db.exists()

    # db.exists() no basta: SqliteMemoryIndex.__init__ ya crea el fichero vía
    # CREATE TABLE IF NOT EXISTS aunque migrate() no llegara a escribir ningún
    # registro. Reabrimos el índice (mismo StubEmbedder, para no chocar con el
    # guard de dimensión) y comprobamos que el cableado CLI->migrate() escribió
    # de verdad registros harness:* — los ids están en claro, no leemos texto.
    index = _test_index(db)
    assert index.ids_by_prefix("harness:") != []
