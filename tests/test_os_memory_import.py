"""Fase 8 Memory OS: import de conversaciones — raw preservado, extracción por
reglas con provenance, idempotencia y eventos reales (no simulados)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.api.conversation_import import import_conversation, list_imported_records
from atlas.api.server import create_app
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent
FIXTURE = json.loads(
    (REPO / "fixtures" / "imports" / "claude_conversation_example.json").read_text()
)
MEMORY_SCHEMA = json.loads((REPO / "schemas" / "memory.schema.json").read_text())


def test_import_preserves_raw_and_extracts(tmp_path: Path) -> None:
    result = import_conversation(FIXTURE, base=tmp_path)
    assert result.raw_preserved
    assert not result.already_imported
    raw_path = Path(result.source_ref)
    assert raw_path.exists(), "la fuente raw DEBE preservarse (§14)"
    assert json.loads(raw_path.read_text()) == FIXTURE, "raw sin mutilar"

    kinds = {r["kind"] for r in result.records}
    assert "decision" in kinds, "Decisión: CRDT sobre SQLite debía extraerse"
    assert "failure" in kinds, "el fallo de Yjs debía extraerse"
    assert "procedural" in kinds, "el patrón snapshot+GC debía extraerse"


def test_records_conform_to_memory_schema(tmp_path: Path) -> None:
    """Validación data-driven contra schemas/memory.schema.json (sin jsonschema)."""
    result = import_conversation(FIXTURE, base=tmp_path)
    required = set(MEMORY_SCHEMA["required"])
    kind_enum = set(MEMORY_SCHEMA["properties"]["kind"]["enum"])
    trust_enum = set(MEMORY_SCHEMA["properties"]["trust"]["enum"])
    for rec in result.records:
        assert required <= set(rec), f"faltan campos required: {required - set(rec)}"
        assert rec["kind"] in kind_enum
        assert rec["trust"] in trust_enum
        assert rec["provenance"]["source"].startswith("import:")
        assert rec["provenance"]["raw_ref"], "provenance sin raw_ref"


def test_import_is_idempotent(tmp_path: Path) -> None:
    first = import_conversation(FIXTURE, base=tmp_path)
    second = import_conversation(FIXTURE, base=tmp_path)
    assert second.already_imported
    assert {r["memory_id"] for r in second.records} == {
        r["memory_id"] for r in first.records
    }
    assert len(list_imported_records(base=tmp_path)) == len(first.records)


def test_endpoint_import_emits_real_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    store = OsEventStore(tmp_path / "events.jsonl")
    client = TestClient(create_app(store=store, fixtures_dir=REPO / "fixtures"))

    body = client.post("/memory/import", json=FIXTURE).json()
    assert body["raw_preserved"] is True
    assert body["record_count"] > 0

    events = store.read()
    imported = [e for e in events if e.type == "source.imported"]
    updated = [e for e in events if e.type == "memory.updated"]
    assert len(imported) == 1 and len(updated) == 1
    assert imported[0].simulated is False, "el import ocurrió de verdad"
    assert imported[0].audit is None, "sin hash Merkle inventado (OS-R9)"

    # segunda llamada: idempotente, sin eventos nuevos
    again = client.post("/memory/import", json=FIXTURE).json()
    assert again["already_imported"] is True
    assert store.count() == len(events)

    listed = client.get("/memory/imports").json()
    assert listed["count"] == body["record_count"]
