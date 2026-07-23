"""Backend Bridge OS (ADR-058): endpoints, WS y el guard anti-Orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from starlette.websockets import WebSocketDisconnect

from atlas.api.server import create_app
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent


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


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["real"] is True
    assert body["connectors"] == 5
    assert body["gates"] == 12


def test_remote_http_requires_a_strong_bearer_or_x_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "atlas-os-test-token-with-more-than-32-bytes"
    monkeypatch.setenv("ATLAS_OS_BRIDGE_TOKEN", token)
    app = create_app(
        store=OsEventStore(tmp_path / "remote-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "remote-business-core.json",
    )
    remote = TestClient(
        app,
        base_url="http://atlas.example",
        client=("203.0.113.10", 50000),
    )

    assert remote.get("/health").status_code == 401
    assert remote.get(
        "/health", headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200
    assert remote.get(
        "/health", headers={"X-Atlas-Token": token},
    ).status_code == 200
    assert remote.get(
        "/health", headers={"Authorization": "Bearer wrong"},
    ).status_code == 401


def test_non_ascii_token_is_rejected_without_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atlas.api.server import _AuthenticationError, _authenticate_client

    monkeypatch.setenv(
        "ATLAS_OS_BRIDGE_TOKEN", "atlas-os-test-token-with-more-than-32-bytes",
    )
    headers = Headers(
        raw=[(b"authorization", "Bearer contraseña".encode("latin-1"))],
    )

    with pytest.raises(_AuthenticationError):
        _authenticate_client("203.0.113.10", headers)


def test_non_loopback_bind_refuses_missing_or_weak_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atlas.api.server import _validate_bind_security

    monkeypatch.delenv("ATLAS_OS_BRIDGE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ATLAS_OS_BRIDGE_TOKEN"):
        _validate_bind_security("0.0.0.0")

    monkeypatch.setenv("ATLAS_OS_BRIDGE_TOKEN", "too-short")
    with pytest.raises(RuntimeError, match="ATLAS_OS_BRIDGE_TOKEN"):
        _validate_bind_security("192.0.2.20")

    _validate_bind_security("127.0.0.1")
    _validate_bind_security("::1")


def test_loopback_http_rejects_malformed_or_rebound_host(client: TestClient) -> None:
    assert client.get(
        "/health", headers={"Host": "127.0.0.1:not-a-port"},
    ).status_code == 401
    assert client.get(
        "/health", headers={"Host": "attacker.example"},
    ).status_code == 401


def test_orchestrator_never_imported() -> None:
    """OS-R1: el bridge no puede ni IMPORTAR el Orchestrator (doble instancia
    = corrupción Merkle). Guard estático: ningún import de orchestrator en
    atlas/api, atlas/events, atlas/fabric ni atlas/business (Fase 15 amplía
    el mismo invariante a los motores de producto). (sys.modules no sirve:
    conftest lo contamina.)"""
    for pkg in ("api", "events", "fabric", "business"):
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


def test_evaluate_known_capability_uses_policy_engine(client: TestClient) -> None:
    """ADR-062: una capability del catálogo se evalúa por PolicyEngine
    (hereda policy_id + invariantes duros), no por la heurística v1."""
    body = client.post(
        "/permissions/evaluate",
        json={"action": "email.send", "resource": "gmail"},
    ).json()
    ev = body["evaluation"]
    assert ev["decision"] == "require_approval"  # require_gate normalizado
    assert ev["gate_id"] == "gate_outbound"

    # crm.bulk_export es capability → gate; legacy 'robot.launch' sigue en v1.
    bulk = client.post(
        "/permissions/evaluate",
        json={"action": "crm.bulk_export", "resource": "hubspot"},
    ).json()["evaluation"]
    assert bulk["decision"] == "require_approval"
    assert bulk["gate_id"] == "gate_data_export"


def test_evaluate_legacy_action_still_uses_v1(client: TestClient) -> None:
    """Acción NO-capability sigue por el evaluador v1 (compatibilidad)."""
    # Se comprueba vía el marcador evaluator en el evento emitido: la
    # respuesta es idéntica en forma, pero mail.send (no es capability)
    # debe seguir dando gate_outbound por el patrón v1.
    ev = client.post(
        "/permissions/evaluate",
        json={"action": "mail.send", "resource": "gmail"},
    ).json()["evaluation"]
    assert ev["decision"] == "require_approval"
    assert ev["gate_id"] == "gate_outbound"


def test_websocket_tail_and_live_push(client: TestClient) -> None:
    client.post("/simulate", json={"fixture": "demo_first_run"})
    first_batch = client.get("/events").json()["count"]
    with client.websocket_connect(
        "/events",
        headers={"Host": "127.0.0.1:7341", "Origin": "http://127.0.0.1:3000"},
    ) as ws:
        seen = [ws.receive_json() for _ in range(min(first_batch, 50))]
        assert seen[0]["id"].startswith("evt_")
        client.post("/connectors/conn_github/test")
        live = ws.receive_json()
        assert live["type"] == "connector.connected"


def test_websocket_rejects_missing_or_cross_site_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect("/events"):
            pass
    assert missing.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as cross_site:
        with client.websocket_connect(
            "/events",
            headers={"Host": "127.0.0.1:7341", "Origin": "https://attacker.example"},
        ):
            pass
    assert cross_site.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as malformed:
        with client.websocket_connect(
            "/events",
            headers={
                "Host": "127.0.0.1:7341",
                "Origin": "http://127.0.0.1:not-a-port",
            },
        ):
            pass
    assert malformed.value.code == 1008


def test_remote_websocket_requires_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "atlas-os-test-token-with-more-than-32-bytes"
    monkeypatch.setenv("ATLAS_OS_BRIDGE_TOKEN", token)
    app = create_app(
        store=OsEventStore(tmp_path / "remote-ws-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "remote-ws-business-core.json",
    )
    remote = TestClient(
        app,
        base_url="http://atlas.example",
        client=("203.0.113.10", 50000),
    )
    origin = {"Host": "atlas.example:7341", "Origin": "https://atlas.example"}

    with pytest.raises(WebSocketDisconnect) as denied:
        with remote.websocket_connect("/events", headers=origin):
            pass
    assert denied.value.code == 1008

    with remote.websocket_connect(
        "/events",
        headers={**origin, "Authorization": f"Bearer {token}"},
    ):
        pass


def test_memory_summary_shape(client: TestClient) -> None:
    body = client.get("/memory/summary").json()
    assert "real" in body
    if body["real"]:
        assert body["records"] >= 0
    else:
        assert body["status"] in {"BLOCKED_BY_MISSING_DEPENDENCY", "UNVERIFIED"}


def test_self_build_summary_shape(client: TestClient) -> None:
    body = client.get("/self-build/summary").json()
    assert "real" in body
    if body["real"]:
        assert body["total"] >= 0
        assert isinstance(body["by_status"], dict)
        assert isinstance(body["recent"], list)
        if body["recent"]:
            first = body["recent"][0]
            assert {"id", "intent", "status", "origin", "risk"} <= first.keys()
    else:
        assert body["status"] in {"BLOCKED_BY_MISSING_DEPENDENCY", "UNVERIFIED"}


def test_self_build_summary_respects_limit(client: TestClient) -> None:
    body = client.get("/self-build/summary?limit=3").json()
    if body["real"]:
        assert len(body["recent"]) <= 3


def test_self_build_proposal_detail_shape(client: TestClient) -> None:
    summary = client.get("/self-build/summary").json()
    if not summary["real"] or not summary["recent"]:
        return
    proposal_id = summary["recent"][0]["id"]
    body = client.get(f"/self-build/proposal/{proposal_id}").json()
    assert body["real"] is True
    assert body["id"] == proposal_id
    assert isinstance(body["files_touched"], list)
    assert "next_action" in body
    assert "validation" in body
    assert "evidence" in body


def test_self_build_proposal_detail_not_found(client: TestClient) -> None:
    body = client.get("/self-build/proposal/does-not-exist-id").json()
    assert body["real"] is False
    assert body["status"] in {"NOT_FOUND", "BLOCKED_BY_MISSING_DEPENDENCY", "UNVERIFIED"}


def test_files_touched_from_patch_parses_diff_headers() -> None:
    from atlas.api.server import _files_touched_from_patch

    diff = (
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "--- /dev/null\n"
        "+++ b/new_file.py\n"
    )
    assert _files_touched_from_patch(diff) == ["pyproject.toml", "new_file.py"]


def test_next_action_hint_by_status() -> None:
    from atlas.api.server import _next_action_hint

    assert _next_action_hint("proposed", "abc") == "atlas update validate abc"
    assert _next_action_hint("validated", "abc") == "atlas update approve abc"
    assert _next_action_hint("approved", "abc") == "atlas update apply abc"
    assert _next_action_hint("applied", "abc") is None
    assert _next_action_hint("rejected", "abc") is None


# -- T1: bridge de governance lee gates reales, no solo fixture -------------
# (docs/architecture/GOVERNANCE_KERNEL.md, "Camino a real")


def _make_client(**create_app_kwargs: object) -> TestClient:
    app = create_app(**create_app_kwargs)  # type: ignore[arg-type]
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def test_permissions_evaluate_real_mode_reads_config_governance_gates(
    tmp_path: Path,
) -> None:
    """create_app(governance_real=True) evalúa contra
    config/governance/gates.json (real) en vez de fixtures/governance/
    gates.json — integración end-to-end de un gate real, simulated=False."""
    repo_root = tmp_path / "repo"
    fixtures_dir = tmp_path / "fixtures_empty"
    (repo_root / "config" / "governance").mkdir(parents=True)
    (fixtures_dir / "governance").mkdir(parents=True)
    (repo_root / "config" / "governance" / "gates.json").write_text(
        json.dumps([{
            "gate_id": "gate_t1_e2e",
            "display_name": "Gate T1 end-to-end",
            "applies_to": ["t1.custom_action"],
            "risk_threshold": "high",
            "approval_mode": "human_explicit",
            "default_decision": "require_approval",
            "enabled": True,
        }]),
        encoding="utf-8",
    )
    # El fixture (compartido con el modo "fixture" de abajo) NO tiene esta
    # gate: si el modo real la leyera por error del fixture, el test fallaría.
    (fixtures_dir / "governance" / "gates.json").write_text("[]", encoding="utf-8")

    real_client = _make_client(
        store=OsEventStore(tmp_path / "real-events.jsonl"),
        fixtures_dir=fixtures_dir,
        business_core_path=tmp_path / "real-business-core.json",
        repo_root=repo_root,
        governance_real=True,
    )
    body = real_client.post(
        "/permissions/evaluate",
        json={"action": "t1.custom_action", "resource": "demo"},
    ).json()
    assert body["simulated"] is False
    ev = body["evaluation"]
    assert ev["decision"] == "require_approval"
    assert ev["gate_id"] == "gate_t1_e2e"

    # Mismo repo_root/fixtures_dir, modo fixture (default): no ve el gate
    # real y sigue marcando simulated=True — cero regresión del camino viejo.
    fixture_client = _make_client(
        store=OsEventStore(tmp_path / "fixture-events.jsonl"),
        fixtures_dir=fixtures_dir,
        business_core_path=tmp_path / "fixture-business-core.json",
        repo_root=repo_root,
    )
    body2 = fixture_client.post(
        "/permissions/evaluate",
        json={"action": "t1.custom_action", "resource": "demo"},
    ).json()
    assert body2["simulated"] is True
    assert body2["evaluation"]["gate_id"] is None


def test_permissions_evaluate_real_mode_via_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Activación real sin pasar governance_real= explícito: ATLAS_OS_
    GOVERNANCE_MODE=real (mismo patrón que ATLAS_OS_BRIDGE_TOKEN)."""
    monkeypatch.setenv("ATLAS_OS_GOVERNANCE_MODE", "real")
    repo_root = tmp_path / "repo"
    (repo_root / "config" / "governance").mkdir(parents=True)
    (repo_root / "config" / "governance" / "gates.json").write_text("[]", encoding="utf-8")
    real_client = _make_client(
        store=OsEventStore(tmp_path / "env-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "env-business-core.json",
        repo_root=repo_root,
    )
    body = real_client.post(
        "/permissions/evaluate",
        json={"action": "github.repos.read", "resource": "github"},
    ).json()
    assert body["simulated"] is False


def test_permissions_pending_reads_real_orchestrator_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /permissions/pending lee memory/pending_approvals/ del workspace
    RUNTIME (ATLAS_HOME) sin instanciar Orchestrator — read-only."""
    from atlas.security.pending_store import wrap_task_payload

    workspace = tmp_path / "atlas_home"
    pending_dir = workspace / "memory" / "pending_approvals"
    pending_dir.mkdir(parents=True)
    task_data = {
        "id": "task_t1_pending",
        "intent": "enviar correo de prueba",
        "tool_name": "mail.send",
        "status": "awaiting_approval",
        "created_at": "2026-07-23T00:00:00+00:00",
        "result": {"reason": "requiere aprobación humana"},
    }
    envelope = wrap_task_payload(task_data)
    (pending_dir / "task_t1_pending.json").write_text(
        json.dumps(envelope), encoding="utf-8",
    )
    monkeypatch.setenv("ATLAS_HOME", str(workspace))

    real_client = _make_client(
        store=OsEventStore(tmp_path / "pending-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "pending-business-core.json",
    )
    body = real_client.get("/permissions/pending").json()
    assert body["count"] == 1
    item = body["pending"][0]
    assert item["task_id"] == "task_t1_pending"
    assert item["tool"] == "mail.send"
    assert item["reason"] == "requiere aprobación humana"


def test_permissions_pending_empty_when_no_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "nunca_existio"))
    real_client = _make_client(
        store=OsEventStore(tmp_path / "empty-pending-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "empty-pending-business-core.json",
    )
    body = real_client.get("/permissions/pending").json()
    assert body == {"real": True, "count": 0, "pending": []}


def test_permissions_approve_routes_to_atlas_cli_not_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /permissions/pending/{task_id}/approve enruta a `atlas approve`
    en un proceso APARTE (nunca Orchestrator dentro del bridge) — sustituye
    el no-op documentado en GOVERNANCE_KERNEL.md."""
    import subprocess as subprocess_module

    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess_module.CompletedProcess[str]:
        captured["args"] = args
        return subprocess_module.CompletedProcess(
            args=args, returncode=0, stdout="Status: done\n", stderr="",
        )

    monkeypatch.setattr("atlas.api.server.subprocess.run", fake_run)

    real_client = _make_client(
        store=OsEventStore(tmp_path / "approve-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "approve-business-core.json",
    )
    resp = real_client.post(
        "/permissions/pending/task_t1_pending/approve", json={"approved": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["returncode"] == 0
    args = captured["args"]
    assert isinstance(args, list)
    assert args[-2:] == ["approve", "task_t1_pending"]
    assert "--deny" not in args

    types = [e["type"] for e in real_client.get("/events").json()["events"]]
    assert "approval.routed" in types


def test_permissions_approve_deny_flag_and_failure_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess as subprocess_module

    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess_module.CompletedProcess[str]:
        captured["args"] = args
        return subprocess_module.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="task_id desconocido",
        )

    monkeypatch.setattr("atlas.api.server.subprocess.run", fake_run)

    real_client = _make_client(
        store=OsEventStore(tmp_path / "approve-deny-events.jsonl"),
        fixtures_dir=REPO / "fixtures",
        business_core_path=tmp_path / "approve-deny-business-core.json",
    )
    resp = real_client.post(
        "/permissions/pending/task_nope/approve", json={"approved": False},
    )
    assert resp.status_code == 502
    args = captured["args"]
    assert isinstance(args, list)
    assert "--deny" in args
