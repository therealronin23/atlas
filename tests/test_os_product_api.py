"""Rutas de producto Fase 15 (/connections, /business) sobre el bridge real."""

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
    return TestClient(create_app(
        store=store, fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "business_core.json",
    ))


# -- Integration Fabric / Easy Connection Layer -------------------------------

def test_connections_catalog_has_categories(client: TestClient) -> None:
    body = client.get("/connections/catalog").json()
    assert "communication" in body["categories"]
    assert body["rejected"] == {}


def test_connections_recipes_lists_all_ten(client: TestClient) -> None:
    body = client.get("/connections/recipes").json()
    assert body["count"] == 10


def test_connections_packs_lists_all_five(client: TestClient) -> None:
    body = client.get("/connections/packs").json()
    assert body["count"] == 5


def test_connections_plan_shows_gates_for_gmail(client: TestClient) -> None:
    body = client.post("/connections/plan", json={"connector_id": "gmail"}).json()
    assert body["connector_id"] == "gmail"
    assert body["requires_gate"][0]["capability"] == "email.send"


def test_connections_plan_unknown_connector_404(client: TestClient) -> None:
    resp = client.post("/connections/plan", json={"connector_id": "does_not_exist"})
    assert resp.status_code == 404


def test_connections_test_mock_ok_and_real_blocked(client: TestClient) -> None:
    mock = client.post("/connections/test",
                       json={"connector_id": "gmail", "mode": "mock"}).json()
    assert mock["ok"] is True
    real = client.post("/connections/test",
                       json={"connector_id": "gmail", "mode": "real"}).json()
    assert real["status"] == "BLOCKED_BY_MISSING_DEPENDENCY"


def test_connections_discover_known_and_unknown(client: TestClient) -> None:
    known = client.get("/connections/discover", params={"target": "gmail"}).json()
    assert known["status"] == "recipe_found"
    unknown = client.get("/connections/discover",
                         params={"target": "totally_unknown_saas"}).json()
    assert unknown["status"] == "unknown_target"


def test_integrations_health_reflects_tests(client: TestClient) -> None:
    client.post("/connections/test", json={"connector_id": "odoo_erp", "mode": "mock"})
    body = client.get("/integrations/health").json()
    ids = {c["connector_id"] for c in body["connectors"]}
    assert "odoo_erp" in ids


# -- Adaptive Question Engine / onboarding end-to-end -------------------------

def test_onboarding_full_loop_via_api(client: TestClient) -> None:
    started = client.post(
        "/business/onboarding/start", json={"pack_id": "qp_restauracion_hosteleria"},
    ).json()
    session_id = started["session_id"]
    assert started["status"] == "active"

    answered = client.post("/business/onboarding/answer", json={
        "session_id": session_id, "question_id": "sales_channels",
        "value": ["local"], "uncertain": False,
    }).json()
    assert any(a["question_id"] == "sales_channels" for a in answered["answers"])

    client.post("/business/onboarding/confirm_answer",
                json={"session_id": session_id, "question_id": "sales_channels"})

    # Sin confirmar el resto, preview debe fallar con 422 (todavía hay pendientes).
    early_preview = client.post("/business/onboarding/preview",
                                json={"session_id": session_id})
    assert early_preview.status_code == 422

    for qid, value in [("has_menu", "no"), ("stock_control", "no")]:
        client.post("/business/onboarding/answer", json={
            "session_id": session_id, "question_id": qid, "value": value,
            "uncertain": False,
        })
        client.post("/business/onboarding/confirm_answer",
                    json={"session_id": session_id, "question_id": qid})
    client.post("/business/onboarding/skip",
                json={"session_id": session_id, "question_id": "uses_pos"})

    preview = client.post("/business/onboarding/preview",
                          json={"session_id": session_id}).json()
    assert preview["status"] == "preview"
    assert preview["proposed"]["entities"]

    confirmed = client.post("/business/onboarding/confirm",
                            json={"session_id": session_id}).json()
    assert confirmed["status"] == "confirmed"


def test_onboarding_unknown_session_404(client: TestClient) -> None:
    resp = client.post("/business/onboarding/answer", json={
        "session_id": "obs_does_not_exist", "question_id": "x", "value": "y",
    })
    assert resp.status_code == 404


# -- Business Core: draft-first + activación gateada --------------------------

def test_business_core_draft_and_gated_activation_via_api(client: TestClient) -> None:
    draft = client.post("/business/core/draft", json={
        "sector_id": "restauracion_hosteleria",
        "created_from_kind": "manual", "created_from_ref": "test",
    }).json()
    core_id = draft["business_core_id"]
    assert draft["status"] == "draft"

    # Activar sin pasar por request-activation: 422.
    direct = client.post("/business/core/activate",
                         json={"business_core_id": core_id, "approved_by": "op"})
    assert direct.status_code == 422

    pending = client.post("/business/core/request-activation",
                          json={"business_core_id": core_id}).json()
    assert pending["status"] == "pending_activation"

    active = client.post("/business/core/activate",
                         json={"business_core_id": core_id, "approved_by": "op"}).json()
    assert active["status"] == "active"
    assert active["activation"]["approved"] is True

    fetched = client.get(f"/business/core/{core_id}").json()
    assert fetched["business_core_id"] == core_id


def test_business_core_unknown_id_404(client: TestClient) -> None:
    resp = client.get("/business/core/bc_does_not_exist")
    assert resp.status_code == 404
    resp2 = client.post("/business/core/request-activation",
                        json={"business_core_id": "bc_does_not_exist"})
    assert resp2.status_code == 404


# -- Gate Engine (Fase 16, ADR-063) ------------------------------------------

def test_gates_queue_reflects_activation_request(client: TestClient) -> None:
    draft = client.post("/business/core/draft", json={
        "sector_id": "restauracion_hosteleria",
        "created_from_kind": "manual", "created_from_ref": "test",
    }).json()
    core_id = draft["business_core_id"]

    assert client.get("/gates/open").json()["count"] == 0
    client.post("/business/core/request-activation", json={"business_core_id": core_id})
    queue = client.get("/gates/open").json()
    assert queue["count"] == 1
    ticket = queue["tickets"][0]
    assert ticket["action"] == "business_core.activate"
    assert ticket["subject_ref"] == core_id

    fetched = client.get(f"/gates/{ticket['gate_ticket_id']}").json()
    assert fetched["status"] == "open"

    # Aprobar activa y vacía la cola.
    client.post("/business/core/activate",
                json={"business_core_id": core_id, "approved_by": "op"})
    assert client.get("/gates/open").json()["count"] == 0


def test_reject_activation_via_api_returns_to_draft(client: TestClient) -> None:
    draft = client.post("/business/core/draft", json={
        "sector_id": "restauracion_hosteleria",
        "created_from_kind": "manual", "created_from_ref": "test",
    }).json()
    core_id = draft["business_core_id"]
    client.post("/business/core/request-activation", json={"business_core_id": core_id})
    rejected = client.post("/business/core/reject", json={
        "business_core_id": core_id, "rejected_by": "op", "decision_note": "no",
    }).json()
    assert rejected["status"] == "draft"
    assert client.get("/gates/open").json()["count"] == 0


def test_gate_unknown_ticket_404(client: TestClient) -> None:
    assert client.get("/gates/gt_nope").status_code == 404
