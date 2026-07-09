"""Tests — ingesta de conocimiento del repo al sustrato de memoria."""

from __future__ import annotations

from pathlib import Path

from atlas.mcp.memory_trunk import MemoryTrunk
from atlas.memory.knowledge_ingest import chunk_markdown, ingest_paths
from atlas.memory.memory_index import SqliteMemoryIndex


def test_chunk_markdown_by_sections() -> None:
    text = "intro\n\n## A\ncuerpo a\n\n## B\ncuerpo b"
    chunks = chunk_markdown(text)
    assert len(chunks) == 3
    assert chunks[1].startswith("## A")
    assert chunks[2].startswith("## B")


def test_chunk_markdown_splits_oversized_section() -> None:
    text = "## Grande\n" + ("párrafo\n\n" * 800)
    chunks = chunk_markdown(text)
    assert len(chunks) > 1
    assert all(len(c) <= 2400 for c in chunks)


def test_ingest_and_recall_roundtrip(tmp_path: Path) -> None:
    """Lo ingerido se recuerda: recall devuelve el chunk con su procedencia."""
    doc = tmp_path / "docs" / "design" / "mini.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "## Fusión Graphify\nLa cadena Graphify-Obsidian-Kuzu convierte código en grafo consultable.",
        encoding="utf-8",
    )

    index = SqliteMemoryIndex(tmp_path / "m.db")
    try:
        trunk = MemoryTrunk(index)
        metrics = ingest_paths(trunk, [doc], repo_root=tmp_path)
        assert metrics == {"docs": 1, "records": 1, "skipped": []}

        hits = trunk.recall("cadena Graphify Obsidian Kuzu grafo", k=3)
        assert hits, "recall vacío tras ingesta"
        assert "docs/design/mini.md" in hits[0].text

        # Idempotencia: re-ingerir no duplica (mismo record_id → upsert).
        ingest_paths(trunk, [doc], repo_root=tmp_path)
        hits2 = trunk.recall("cadena Graphify Obsidian Kuzu grafo", k=5)
        ids = [h.record_id for h in hits2]
        assert len(ids) == len(set(ids))
        assert ids.count("ki:docs/design/mini.md#0") == 1
    finally:
        index.close()
