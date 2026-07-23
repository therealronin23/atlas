"""Mission Layer v0 (Foundry, ADR-069): contratos, adapter ColdUpdate→Mission,
receipt determinista y radar proactivo. Todo read-only: las funciones son puras
sobre dicts del ledger (`proposals.json`), jamás instancian ColdUpdateManager.

Spec: docs/design/mission_layer_self_construction_spec.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from atlas.api.missions import (
    ecosystem_drift_mission,
    ecosystem_drift_receipt,
    mission_receipt,
    missions_payload,
    proposal_to_mission,
    radar_findings,
)
from atlas.api.server import create_app
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _proposal(**overrides: Any) -> dict[str, Any]:
    """Propuesta realista del ledger (misma forma que proposals.json real)."""
    base: dict[str, Any] = {
        "id": "48a246ef-b1f",
        "intent": "bump dependencia fastapi 0.110 → 0.136.3",
        "status": "validated",
        "origin": "self_audit",
        "risk": "low",
        "base_ref": "HEAD",
        "created_at": "2026-07-15T10:18:24.103355+00:00",
        "updated_at": "2026-07-15T11:20:18.694510+00:00",
        "evidence": {"dependency": "fastapi", "from": "0.110", "to": "0.136.3"},
        "validation": {"passed": True, "pytest_exit": 0, "mypy_exit": 0},
        "patch_path": "/tmp/worktree-x/proposal.patch",
        "worktree_path": "/tmp/worktree-x",
        "forensics": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- contratos

def test_mission_schemas_are_valid_jsonschema() -> None:
    for name in ("mission", "mission_receipt", "soul_manifest"):
        schema = json.loads((REPO / "schemas" / f"{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["title"].startswith("Atlas")


# ------------------------------------------------------- adapter → Mission

def test_proposal_to_mission_maps_real_fields() -> None:
    mission = proposal_to_mission(_proposal(), files_touched=["pyproject.toml"])
    assert mission["mission_id"] == "msn_48a246ef-b1f"
    assert mission["intent"].startswith("bump dependencia fastapi")
    assert mission["state"] == "awaiting_human_approval"  # validated → decisión humana
    assert mission["risk"] == "low"
    assert mission["origin"] == "self_audit"
    assert mission["source"] == {"kind": "cold_update_proposal", "ref": "48a246ef-b1f"}
    assert mission["artifacts"] == ["pyproject.toml"]
    assert mission["evidence_bundle"]["validation"]["passed"] is True
    assert mission["human_action_required"] is True
    assert mission["next_action"]["command"] == "atlas update approve 48a246ef-b1f"
    assert mission["next_action"]["actor"] == "human"


@pytest.mark.parametrize(
    ("status", "state", "human"),
    [
        ("proposed", "plan_proposed", True),
        ("validated", "awaiting_human_approval", True),
        ("approved", "approved_pending_apply", True),
        ("applied", "applied", False),
        ("failed", "failed", False),
        ("rejected", "rejected", False),
        ("garbage", "unknown", False),
    ],
)
def test_ledger_status_to_mission_state(status: str, state: str, human: bool) -> None:
    mission = proposal_to_mission(_proposal(status=status))
    assert mission["state"] == state
    assert mission["human_action_required"] is human


def test_adapter_output_conforms_to_mission_schema() -> None:
    """El adapter debe producir misiones que VALIDAN contra el contrato —
    el schema no es decoración."""
    schema = json.loads((REPO / "schemas" / "mission.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for status in ("proposed", "validated", "applied", "failed", "rejected"):
        mission = proposal_to_mission(_proposal(status=status))
        errors = list(validator.iter_errors(mission))
        assert not errors, f"status={status}: {[e.message for e in errors]}"


# ----------------------------------------------------------------- receipt

def test_mission_receipt_is_honest_and_verifiable() -> None:
    receipt = mission_receipt(_proposal(), files_touched=["pyproject.toml"])
    assert receipt["receipt_id"] == "rcp_48a246ef-b1f"
    assert receipt["mission_id"] == "msn_48a246ef-b1f"
    # las 5 preguntas del receipt (export L65445): qué pasó / por qué importa /
    # qué hizo Atlas / qué falta / qué decisión se necesita
    for field in ("what_happened", "why_it_matters", "what_atlas_did",
                  "whats_missing", "decision_needed"):
        assert receipt[field], field
    assert "atlas update approve 48a246ef-b1f" in receipt["decision_needed"]
    # evidencia = referencias comprobables reales, no prosa
    assert any("pytest_exit=0" in ref for ref in receipt["evidence_refs"])
    assert receipt["verifiable"] is True


def test_mission_receipt_without_validation_says_so() -> None:
    receipt = mission_receipt(_proposal(status="proposed", validation=None))
    assert receipt["verifiable"] is False
    assert "sin validación" in receipt["whats_missing"].lower()


def test_receipt_conforms_to_receipt_schema() -> None:
    schema = json.loads((REPO / "schemas" / "mission_receipt.schema.json").read_text())
    validator = Draft202012Validator(schema)
    receipt = mission_receipt(_proposal())
    errors = list(validator.iter_errors(receipt))
    assert not errors, [e.message for e in errors]


# ------------------------------------------------------------------- radar

def test_radar_detects_repeated_proposal() -> None:
    """El caso real conocido (ADR-068 Act. 2): mismo intent re-propuesto sin
    converger nunca a applied — el radar debe señalarlo, no esperar al humano."""
    proposals = [
        _proposal(id=f"rep-{i}", intent="Cablear el vault Obsidian al tick del grafo",
                  status="proposed",
                  updated_at=(NOW - timedelta(hours=i)).isoformat())
        for i in range(4)
    ]
    findings = radar_findings(proposals, now=NOW)
    repeated = [f for f in findings if f["detector"] == "repeated_proposal"]
    assert len(repeated) == 1
    assert repeated[0]["severity"] == "radar"
    assert len(repeated[0]["mission_ids"]) == 4
    assert "4" in repeated[0]["summary"]


def test_radar_repeated_ignores_intents_that_converged() -> None:
    proposals = [
        _proposal(id=f"ok-{i}", intent="mismo intent", status=s)
        for i, s in enumerate(["proposed", "proposed", "applied"])
    ]
    findings = radar_findings(proposals, now=NOW)
    assert not [f for f in findings if f["detector"] == "repeated_proposal"]


def test_radar_detects_stale_proposal() -> None:
    old = (NOW - timedelta(hours=72)).isoformat()
    findings = radar_findings([_proposal(status="proposed", updated_at=old)], now=NOW)
    stale = [f for f in findings if f["detector"] == "stale_proposal"]
    assert len(stale) == 1
    assert stale[0]["severity"] == "radar"


def test_radar_detects_missing_validation() -> None:
    findings = radar_findings(
        [_proposal(status="proposed", validation=None)], now=NOW
    )
    missing = [f for f in findings if f["detector"] == "validation_missing"]
    assert len(missing) == 1


def test_radar_gate_pending_asks_for_human() -> None:
    findings = radar_findings([_proposal(status="validated")], now=NOW)
    gate = [f for f in findings if f["detector"] == "gate_pending"]
    assert len(gate) == 1
    assert gate[0]["severity"] == "ask"


def test_radar_quiet_on_healthy_history() -> None:
    """Historial sano (aplicadas/rechazadas antiguas) → radar en silencio."""
    proposals = [
        _proposal(id=f"h-{i}", intent=f"intent {i}", status="applied")
        for i in range(5)
    ] + [
        _proposal(id=f"r-{i}", intent=f"otro {i}", status="rejected")
        for i in range(5)
    ]
    assert radar_findings(proposals, now=NOW) == []


# ------------------------------------------------ T1.3 radar → misión NUEVA
# (ecosystem_drift): el radar hoy solo proyecta hallazgos sobre proposals ya
# existentes; estos tests demuestran que un hallazgo de ecosystem_drift (NO
# derivado de un proposal existente) genera una AtlasMission draft nueva,
# nunca auto-aprobada.

def test_ecosystem_drift_mission_is_none_without_drift() -> None:
    assert ecosystem_drift_mission([], now=NOW) is None


def test_ecosystem_drift_mission_builds_draft_mission() -> None:
    drift = ["ADR-999 (adr_999_test.md) sin fila en docs/design/atlas_ecosystem_map.md"]
    mission = ecosystem_drift_mission(drift, now=NOW)
    assert mission is not None
    assert mission["mission_id"].startswith("msn_ecodrift-")
    assert mission["state"] == "plan_proposed"
    assert mission["risk"] == "low"
    assert mission["source"]["kind"] == "ecosystem_drift"
    assert mission["human_action_required"] is True
    assert mission["next_action"]["actor"] == "human"
    # nunca auto-aprobada/aplicada: el next_action nunca es un comando de
    # aprobar/aplicar — solo puede señalar a un humano a crear una propuesta
    # real con `atlas update propose`.
    assert "approve" not in mission["next_action"]["command"]
    assert "apply" not in mission["next_action"]["command"]
    assert mission["evidence_bundle"]["evidence"]["drift"] == drift


def test_ecosystem_drift_mission_is_stable_regardless_of_order() -> None:
    """Mismo hallazgo (aunque llegue en otro orden) → misma mission_id, para
    que el radar no genere una misión duplicada en cada tick."""
    drift = ["ADR-1 sin fila", "ADR-2 sin fila"]
    m1 = ecosystem_drift_mission(drift, now=NOW)
    m2 = ecosystem_drift_mission(list(reversed(drift)), now=NOW)
    assert m1 is not None and m2 is not None
    assert m1["mission_id"] == m2["mission_id"]


def test_ecosystem_drift_mission_conforms_to_mission_schema() -> None:
    schema = json.loads((REPO / "schemas" / "mission.schema.json").read_text())
    validator = Draft202012Validator(schema)
    mission = ecosystem_drift_mission(["ADR-1 sin fila"], now=NOW)
    assert mission is not None
    errors = list(validator.iter_errors(mission))
    assert not errors, [e.message for e in errors]


def test_ecosystem_drift_receipt_is_honest_and_unverifiable() -> None:
    mission = ecosystem_drift_mission(["ADR-1 sin fila"], now=NOW)
    assert mission is not None
    receipt = ecosystem_drift_receipt(mission)
    assert receipt["mission_id"] == mission["mission_id"]
    assert receipt["verifiable"] is False  # nadie ha validado nada: solo hay un hallazgo
    for field in ("what_happened", "why_it_matters", "what_atlas_did",
                  "whats_missing", "decision_needed"):
        assert receipt[field], field


def test_ecosystem_drift_receipt_conforms_to_receipt_schema() -> None:
    schema = json.loads((REPO / "schemas" / "mission_receipt.schema.json").read_text())
    validator = Draft202012Validator(schema)
    mission = ecosystem_drift_mission(["ADR-1 sin fila"], now=NOW)
    assert mission is not None
    receipt = ecosystem_drift_receipt(mission)
    errors = list(validator.iter_errors(receipt))
    assert not errors, [e.message for e in errors]


def test_radar_findings_surfaces_ecosystem_drift() -> None:
    findings = radar_findings([], now=NOW, drift=["ADR-1 sin fila"])
    drift_findings = [f for f in findings if f["detector"] == "ecosystem_drift"]
    assert len(drift_findings) == 1
    assert drift_findings[0]["severity"] == "ask"
    assert drift_findings[0]["mission_ids"][0].startswith("msn_ecodrift-")


def test_radar_findings_silent_without_drift() -> None:
    findings = radar_findings([], now=NOW, drift=[])
    assert not [f for f in findings if f["detector"] == "ecosystem_drift"]
    findings_default = radar_findings([], now=NOW)  # drift ni se pasa
    assert not [f for f in findings_default if f["detector"] == "ecosystem_drift"]


def test_missions_payload_includes_extra_missions() -> None:
    mission = ecosystem_drift_mission(["ADR-1 sin fila"], now=NOW)
    assert mission is not None
    body = missions_payload([], limit=10, extra_missions=[mission])
    assert body["total"] == 1
    assert body["missions"][0]["mission_id"] == mission["mission_id"]
    assert body["missions"][0]["human_action_required"] is True
    assert body["by_state"]["plan_proposed"] == 1


def test_missions_payload_without_extra_missions_unaffected() -> None:
    proposals = [_proposal(id="a", status="proposed")]
    assert missions_payload(proposals, limit=10) == missions_payload(
        proposals, limit=10, extra_missions=None
    )


# ------------------------------------------------------------ payload/API

def test_missions_payload_aggregates() -> None:
    proposals = [
        _proposal(id="a", status="proposed"),
        _proposal(id="b", status="validated"),
        _proposal(id="c", status="applied"),
    ]
    body = missions_payload(proposals, limit=2)
    assert body["real"] is True
    assert body["total"] == 3
    assert body["by_state"]["awaiting_human_approval"] == 1
    assert len(body["missions"]) == 2
    # activas (con acción humana pendiente) primero
    assert body["missions"][0]["human_action_required"] is True


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    store = OsEventStore(tmp_path / "events.jsonl")
    return TestClient(
        create_app(
            store=store,
            fixtures_dir=REPO / "fixtures",
            business_core_path=tmp_path / "business_core.json",
        ),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def test_missions_endpoint_shape(client: TestClient) -> None:
    body = client.get("/missions?limit=5").json()
    assert "real" in body
    if body["real"]:
        assert body["total"] >= 0
        assert isinstance(body["missions"], list)
        assert len(body["missions"]) <= 5
        if body["missions"]:
            first = body["missions"][0]
            assert {"mission_id", "intent", "state", "risk",
                    "human_action_required"} <= first.keys()
    else:
        assert body["status"] in {"BLOCKED_BY_MISSING_DEPENDENCY", "UNVERIFIED"}


def test_mission_detail_endpoint_includes_receipt(client: TestClient) -> None:
    listing = client.get("/missions?limit=1").json()
    if not listing.get("real") or not listing["missions"]:
        return
    mission_id = listing["missions"][0]["mission_id"]
    body = client.get(f"/missions/{mission_id}").json()
    assert body["real"] is True
    assert body["mission"]["mission_id"] == mission_id
    assert body["receipt"]["mission_id"] == mission_id
    assert isinstance(body["mission"]["artifacts"], list)


def test_mission_detail_not_found(client: TestClient) -> None:
    body = client.get("/missions/msn_does-not-exist").json()
    assert body["real"] is False
    assert body["status"] in {"NOT_FOUND", "BLOCKED_BY_MISSING_DEPENDENCY",
                              "UNVERIFIED"}


def test_radar_endpoint_shape(client: TestClient) -> None:
    body = client.get("/missions/radar").json()
    assert "real" in body
    if body["real"]:
        assert isinstance(body["findings"], list)
        for f in body["findings"]:
            assert f["severity"] in {"silent", "radar", "ask", "gate"}


def _client_with_repo_root(tmp_path: Path, repo_root: Path) -> TestClient:
    store = OsEventStore(tmp_path / "events.jsonl")
    return TestClient(
        create_app(
            store=store,
            fixtures_dir=REPO / "fixtures",
            business_core_path=tmp_path / "business_core.json",
            repo_root=repo_root,
        ),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def test_missions_endpoint_surfaces_synthetic_ecosystem_drift(tmp_path: Path) -> None:
    """T1.3: un ADR real sin fila en el mapa (hallazgo NO derivado de ningún
    proposal existente) debe aparecer en GET /missions como misión draft
    nueva, con human_action_required=true — sin que nada la haya aplicado."""
    drift_root = tmp_path / "repo"
    adr_dir = drift_root / "docs" / "decisions" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "adr_999_test_drift.md").write_text("# ADR 999 de prueba\n", encoding="utf-8")
    design_dir = drift_root / "docs" / "design"
    design_dir.mkdir(parents=True)
    (design_dir / "atlas_ecosystem_map.md").write_text("sin citas aqui\n", encoding="utf-8")

    test_client = _client_with_repo_root(tmp_path, drift_root)

    body = test_client.get("/missions").json()
    if not body["real"]:
        pytest.skip(f"proposals.json no disponible en este entorno: {body}")
    drift_missions = [m for m in body["missions"] if m["source"]["kind"] == "ecosystem_drift"]
    assert len(drift_missions) == 1
    assert drift_missions[0]["human_action_required"] is True
    assert drift_missions[0]["next_action"] is not None
    assert "approve" not in drift_missions[0]["next_action"]["command"]
    assert "apply" not in drift_missions[0]["next_action"]["command"]

    radar_body = test_client.get("/missions/radar").json()
    if radar_body["real"]:
        assert any(f["detector"] == "ecosystem_drift" for f in radar_body["findings"])


def test_missions_endpoint_silent_when_no_drift(tmp_path: Path) -> None:
    """Repo sin ADRs (o todos citados) → ningún hallazgo sintético; el radar
    no inventa misiones de la nada."""
    drift_root = tmp_path / "repo"
    (drift_root / "docs" / "decisions" / "adr").mkdir(parents=True)
    (drift_root / "docs" / "design").mkdir(parents=True)

    test_client = _client_with_repo_root(tmp_path, drift_root)
    body = test_client.get("/missions").json()
    if not body["real"]:
        pytest.skip(f"proposals.json no disponible en este entorno: {body}")
    drift_missions = [m for m in body["missions"] if m["source"]["kind"] == "ecosystem_drift"]
    assert drift_missions == []
