"""Event store OS + player + bridge del bus real (ADR-058)."""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.contracts import Event, EventType
from atlas.core.event_bus import EventBus
from atlas.events.core_bridge import CoreEventBridge, project_core_event
from atlas.events.player import EventPlayer
from atlas.events.schemas import OsEvent, Risk
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent
FIRST_RUN = REPO / "fixtures" / "events" / "demo_first_run.jsonl"


def _event(i: int = 1) -> OsEvent:
    return OsEvent.model_validate(
        {
            "id": f"evt_store_{i}",
            "type": "intent.created",
            "timestamp": "2026-07-10T00:00:00Z",
            "schema_version": "1.0",
            "source": "atlas.test",
            "summary": f"evento {i}",
            "status": "completed",
            "risk": "none",
            "visible": True,
            "payload": {"i": i},
        }
    )


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    for i in range(5):
        store.append(_event(i))
    assert store.count() == 5
    assert [e.payload["i"] for e in store.read(limit=2)] == [0, 1]
    assert [e.payload["i"] for e in store.tail(2)] == [3, 4]


def test_listener_notified_and_broken_listener_isolated(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    seen: list[str] = []

    def broken(_: OsEvent) -> None:
        raise RuntimeError("listener roto")

    store.subscribe(broken)
    store.subscribe(lambda e: seen.append(e.id))
    store.append(_event(7))
    assert seen == ["evt_store_7"]
    assert store.count() == 1


def test_player_marks_simulated(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    result = EventPlayer(store).play_fixture(FIRST_RUN)
    assert result.status == "completed"
    assert result.event_count > 0
    assert result.errors == []
    events = store.read()
    assert len(events) == result.event_count
    assert all(e.simulated is True for e in events)


def test_player_rejects_fixture_with_merkle_hash(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    fake = _event(1).model_dump()
    fake["audit"] = {"merkle_hash": "deadbeef", "previous_hash": None}
    fixture = tmp_path / "bad.jsonl"
    fixture.write_text(json.dumps(fake) + "\n")
    result = EventPlayer(store).play_fixture(fixture)
    assert result.event_count == 0
    assert result.status == "failed"
    assert "merkle_hash" in result.errors[0]
    assert store.count() == 0


def test_player_missing_fixture_fails_clean(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    result = EventPlayer(store).play_fixture(tmp_path / "no_existe.jsonl")
    assert result.status == "failed"
    assert result.errors


def test_core_bridge_projects_real_events(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    bus = EventBus()
    CoreEventBridge(bus, store).attach()

    bus.publish_type(EventType.SECURITY_VIOLATION, {"detail": "x"}, task_id="t1")
    events = store.read()
    assert len(events) == 1
    projected = events[0]
    assert projected.type == EventType.SECURITY_VIOLATION.value
    assert projected.simulated is False
    assert projected.risk == Risk.HIGH
    assert projected.process_id == "t1"
    assert projected.audit is None  # el bridge jamás inventa hashes (OS-R9)


def test_projection_is_valid_os_event() -> None:
    core_evt = Event(type=EventType.SECURITY_VIOLATION, payload={"a": 1})
    projected = project_core_event(core_evt)
    # revalidar por JSON garantiza compatibilidad con el schema serializado
    OsEvent.model_validate_json(projected.model_dump_json())
