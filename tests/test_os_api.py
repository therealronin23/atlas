"""Backend Bridge OS (ADR-058): endpoints, WS y el guard anti-Orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.api.server import create_app
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    store = OsEventStore(tmp_path / "events.jsonl")
    return TestClient(create_app(store=store, fixtures_dir=REPO / "fixtures"))


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["real"] is True
    assert body["connectors"] == 5
    assert body["gates"] == 4


def test_orchestrator_never_imported() -> None:
    """OS-R1: el bridge no puede ni IMPORTAR el Orchestrator (doble instancia
    = corrupción Merkle). Guard estático: ningún import de orchestrator en
    atlas/api ni atlas/events. (sys.modules no sirve: conftest lo contamina.)"""
    for pkg in ("api", "events"):
        for path in (REPO / "src" / "atlas" / pkg).rglob("*.py"):
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")) and "orchestrator" in stripped:
                    pytest.fail(f"{path.name}:{lineno} importa orchestrator: {stripped}")


def test_graph_is_marked_simulated(client: TestClient) -> None:
    body = client.get("/graph").json()
    assert body["simulated"] is True
    assert body["nodes"] and body["edges"]


def test_intent_pipeline_chained_and_simulated(client: TestClient) -> None:
    body = client.post("/intent", json={"text": "analiza el proyecto"}).json()
    events = body["events"]
    assert body["simulated"] is True
    assert [e["type"] for e in events][:2] == ["intent.created", "intent.classified"]
    assert all(e["simulated"] for e in events)
    assert events[0]["payload"]["text"] == "analiza el proyecto"
    # cadena causal: cada evento apunta al anterior, mismo trace
    traces = {e["causality"]["trace_id"] for e in events if e["causality"]}
    assert len(traces) == 1
    for prev, curr in zip(events, events[1:]):
        assert curr["causality"]["parent_event_id"] == prev["id"]
    # y quedó persistido en el store
    assert client.get("/events").json()["count"] == len(events)


def test_simulate_fixture_and_timeline(client: TestClient) -> None:
    body = client.post("/simulate", json={"fixture": "demo_first_run"}).json()
    assert body["status"] == "completed"
    assert body["event_count"] > 0
    timeline = client.get("/timeline").json()
    assert timeline["count"] == body["event_count"]


def test_simulate_unknown_fixture_404(client: TestClient) -> None:
    assert client.post("/simulate", json={"fixture": "nope"}).status_code == 404


def test_simulate_rejects_path_traversal(client: TestClient) -> None:
    # el modelo solo admite [A-Za-z0-9_-]+ → 422 de validación
    resp = client.post("/simulate", json={"fixture": "../../etc/passwd"})
    assert resp.status_code == 422


def test_connectors_listed_without_secrets(client: TestClient) -> None:
    body = client.get("/connectors").json()
    assert body["count"] == 5
    for conn in body["connectors"]:
        ref = conn["credential_reference"]
        assert ref is None or ref.startswith("env:"), "solo referencias opacas"
        assert conn["mode"] == "mock"


def test_connector_test_and_sync_emit_events(client: TestClient) -> None:
    assert client.post("/connectors/conn_github/test").json()["simulated"] is True
    body = client.post("/connectors/conn_github/sync").json()
    assert body["ok"] is True
    types = [e["type"] for e in client.get("/events").json()["events"]]
    assert "connector.connected" in types
    assert "connector.sync.started" in types
    assert "connector.sync.finished" in types


def test_connector_unknown_404(client: TestClient) -> None:
    assert client.post("/connectors/conn_nope/test").status_code == 404


def test_evaluate_outbound_requires_approval(client: TestClient) -> None:
    body = client.post(
        "/permissions/evaluate",
        json={"action": "mail.send", "resource": "gmail"},
    ).json()
    ev = body["evaluation"]
    assert ev["decision"] == "require_approval"
    assert ev["gate_id"] == "gate_outbound"


def test_evaluate_credentials_always_blocked(client: TestClient) -> None:
    ev = client.post(
        "/permissions/evaluate",
        json={"action": "credentials.rotate", "resource": "vault"},
    ).json()["evaluation"]
    assert ev["decision"] == "deny"
    assert ev["gate_id"] == "gate_credentials"


def test_evaluate_read_allowed_and_unknown_fail_closed(client: TestClient) -> None:
    allow = client.post(
        "/permissions/evaluate",
        json={"action": "github.repos.read", "resource": "github"},
    ).json()["evaluation"]
    assert allow["decision"] == "allow"
    unknown = client.post(
        "/permissions/evaluate",
        json={"action": "robot.launch", "resource": "lab"},
    ).json()["evaluation"]
    assert unknown["decision"] == "require_approval", "fail-closed"


def test_websocket_tail_and_live_push(client: TestClient) -> None:
    client.post("/simulate", json={"fixture": "demo_first_run"})
    first_batch = client.get("/events").json()["count"]
    with client.websocket_connect("/events") as ws:
        seen = [ws.receive_json() for _ in range(min(first_batch, 50))]
        assert seen[0]["id"].startswith("evt_")
        client.post("/connectors/conn_github/test")
        live = ws.receive_json()
        assert live["type"] == "connector.connected"


def test_memory_summary_shape(client: TestClient) -> None:
    body = client.get("/memory/summary").json()
    assert "real" in body
    if body["real"]:
        assert body["records"] >= 0
    else:
        assert body["status"] in {"BLOCKED_BY_MISSING_DEPENDENCY", "UNVERIFIED"}
