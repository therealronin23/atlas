"""Contracts-first: los fixtures y los JSON Schema son la verdad; los modelos
pydantic de atlas.events.schemas deben validar exactamente lo mismo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.events.schemas import GraphEdge, GraphNode, OsEvent

REPO = Path(__file__).resolve().parent.parent
FIXTURE_EVENTS = sorted((REPO / "fixtures" / "events").glob("*.jsonl"))
GRAPH_FIXTURE = REPO / "fixtures" / "graph" / "initial_graph.json"
EVENT_SCHEMA = json.loads((REPO / "schemas" / "event.schema.json").read_text())


def _base_event(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "evt_test",
        "type": "intent.created",
        "timestamp": "2026-07-10T00:00:00Z",
        "schema_version": "1.0",
        "source": "atlas.test",
        "summary": "evento de test",
        "status": "completed",
        "risk": "none",
        "visible": True,
        "payload": {},
    }
    data.update(overrides)
    return data


def test_fixtures_exist() -> None:
    assert len(FIXTURE_EVENTS) >= 5, "el prompt exige 5 fixtures de eventos"
    assert GRAPH_FIXTURE.exists()


@pytest.mark.parametrize("fixture", FIXTURE_EVENTS, ids=lambda p: p.name)
def test_every_fixture_line_validates(fixture: Path) -> None:
    lines = [ln for ln in fixture.read_text().splitlines() if ln.strip()]
    assert lines, f"{fixture.name} está vacío"
    for lineno, raw in enumerate(lines, start=1):
        event = OsEvent.model_validate_json(raw)
        assert event.id.startswith("evt_"), f"{fixture.name}:{lineno}"


def test_graph_fixture_validates() -> None:
    graph = json.loads(GRAPH_FIXTURE.read_text())
    nodes = [GraphNode.model_validate(n) for n in graph["nodes"]]
    edges = [GraphEdge.model_validate(e) for e in graph["edges"]]
    assert nodes and edges
    node_ids = {n.id for n in nodes}
    for edge in edges:
        assert edge.source in node_ids, f"arista {edge.id}: source huérfano"
        assert edge.target in node_ids, f"arista {edge.id}: target huérfano"


def test_model_mirrors_json_schema_required_fields() -> None:
    """Paridad modelo↔schema: todo campo required del JSON Schema es
    obligatorio en el modelo (sin default) y viceversa."""
    schema_required = set(EVENT_SCHEMA["required"])
    model_required = {
        name for name, f in OsEvent.model_fields.items() if f.is_required()
    }
    # schema_version tiene default en el modelo por ergonomía; el resto igual.
    assert schema_required - {"schema_version"} == model_required
    assert set(EVENT_SCHEMA["properties"]) == set(OsEvent.model_fields)


def test_model_mirrors_json_schema_enums() -> None:
    from atlas.events.schemas import EventStatus, Risk

    assert {s.value for s in EventStatus} == set(
        EVENT_SCHEMA["properties"]["status"]["enum"]
    )
    assert {r.value for r in Risk} == set(EVENT_SCHEMA["properties"]["risk"]["enum"])


def test_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OsEvent.model_validate(_base_event(inventado=1))


def test_rejects_bad_id_pattern() -> None:
    with pytest.raises(ValidationError):
        OsEvent.model_validate(_base_event(id="event-123"))


def test_rejects_bad_status_and_risk() -> None:
    with pytest.raises(ValidationError):
        OsEvent.model_validate(_base_event(status="doing"))
    with pytest.raises(ValidationError):
        OsEvent.model_validate(_base_event(risk="extreme"))


def test_all_root_schemas_are_valid_json() -> None:
    schemas = sorted((REPO / "schemas").glob("*.schema.json"))
    assert len(schemas) == 29, ("12 Fase 2 + 10 Fase 15 + 4 Fase 16 (gate_ticket, sector, "
                                "objective, platform_terms) + 3 Foundry v0 ADR-069 "
                                "(mission, mission_receipt, soul_manifest)")
    for path in schemas:
        doc = json.loads(path.read_text())
        assert doc["type"] == "object", path.name
        assert doc["required"], path.name
