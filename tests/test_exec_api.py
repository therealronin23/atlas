"""
ADR-027 tests — /api/exec/* endpoints.

Covers:
  - HMAC verification (good signature accepted, bad rejected, missing 503)
  - Timestamp drift defence (replay protection)
  - shell endpoint happy path + capability-denied path
  - file read/write endpoints
  - Merkle audit entries land for each refusal and success
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas.core.orchestrator import Orchestrator
from atlas.interfaces.exec_api import (
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    build_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SECRET = "test-secret-hermes-key-abc123"


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("HERMES_API_KEY", SECRET)
    return Orchestrator(workspace=tmp_path / "atlas")


@pytest.fixture
def client(orch: Orchestrator) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(lambda: orch))
    return TestClient(app)


def _sign(body: bytes) -> dict[str, str]:
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        HEADER_SIGNATURE: sig,
        HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# HMAC auth
# ---------------------------------------------------------------------------


class TestHmacAuth:

    def test_missing_signature_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo", "args": ["hi"]}).encode()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        })
        assert r.status_code == 401

    def test_bad_signature_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: "deadbeef" * 8,
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        })
        assert r.status_code == 401

    def test_stale_timestamp_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        stale_ts = "2020-01-01T00:00:00+00:00"
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: sig,
            HEADER_TIMESTAMP: stale_ts,
        })
        assert r.status_code == 401

    def test_missing_timestamp_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: sig,
        })
        assert r.status_code == 401

    def test_no_secret_returns_503(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        app = FastAPI()
        app.include_router(build_router(lambda: orch))
        c = TestClient(app)
        body = json.dumps({"command": "echo"}).encode()
        r = c.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: "x" * 64,
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        })
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# /api/exec/shell
# ---------------------------------------------------------------------------


class TestExecShell:

    def test_allowed_command_returns_ok(self, client: TestClient) -> None:
        # `git` is in the default shell_allowlist
        body = json.dumps({"command": "git", "args": ["status"]}).encode()
        r = client.post("/api/exec/shell", content=body, headers=_sign(body))
        # Should be 200 even if git status returns non-zero (no git repo)
        assert r.status_code == 200
        data = r.json()
        assert "returncode" in data
        assert "stdout" in data
        assert "stderr" in data

    def test_disallowed_command_returns_403(self, client: TestClient) -> None:
        body = json.dumps({"command": "sudo", "args": ["rm", "-rf", "/"]}).encode()
        r = client.post("/api/exec/shell", content=body, headers=_sign(body))
        assert r.status_code == 403

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        body = b"not json"
        r = client.post("/api/exec/shell", content=body, headers=_sign(body))
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/exec/file
# ---------------------------------------------------------------------------


class TestExecFile:

    def test_write_then_read_roundtrip(
        self, client: TestClient, orch: Orchestrator, tmp_path: Path,
    ) -> None:
        # tmp/ is writable per default PermissionProfile
        target = "tmp/exec_api_test.txt"
        (orch._workspace / "tmp").mkdir(parents=True, exist_ok=True)

        write_body = json.dumps({
            "action": "write",
            "path": str(orch._workspace / target),
            "data": "atlas via hermes",
        }).encode()
        r = client.post("/api/exec/file", content=write_body, headers=_sign(write_body))
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        read_body = json.dumps({
            "action": "read",
            "path": str(orch._workspace / target),
        }).encode()
        r2 = client.post("/api/exec/file", content=read_body, headers=_sign(read_body))
        assert r2.status_code == 200, r2.text
        assert r2.json()["data"] == "atlas via hermes"

    def test_bad_action_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"action": "delete", "path": "/etc/passwd"}).encode()
        r = client.post("/api/exec/file", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_blocked_path_returns_403(self, client: TestClient) -> None:
        body = json.dumps({"action": "read", "path": "/etc/passwd"}).encode()
        r = client.post("/api/exec/file", content=body, headers=_sign(body))
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class TestExecIntent:

    def test_intent_runs_pipeline(self, client: TestClient) -> None:
        body = json.dumps({"intent": "echo test from hermes"}).encode()
        r = client.post("/api/exec/intent", content=body, headers=_sign(body))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] in {"done", "failed", "blocked"}

    def test_intent_empty_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"intent": "   "}).encode()
        r = client.post("/api/exec/intent", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_intent_missing_returns_400(self, client: TestClient) -> None:
        body = json.dumps({}).encode()
        r = client.post("/api/exec/intent", content=body, headers=_sign(body))
        assert r.status_code == 400


class TestExecAudit:

    def test_records_hermes_action(self, client: TestClient, orch: Orchestrator) -> None:
        body = json.dumps({
            "action": "skill.run",
            "result": "success",
            "risk_level": "moderate",
            "payload": {"skill": "weather"},
        }).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        # provenance: namespaced action + chained hashes returned as a receipt
        assert data["action"] == "hermes.skill.run"
        assert len(data["hash_self"]) == 64
        rec = orch._merkle.tail(1)[0]
        assert rec.agent == "hermes_vps"
        assert rec.action == "hermes.skill.run"

    def test_already_namespaced_action_not_double_prefixed(self, client: TestClient) -> None:
        body = json.dumps({"action": "hermes.cron.tick"}).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 200
        assert r.json()["action"] == "hermes.cron.tick"

    def test_missing_action_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"result": "success"}).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_bad_result_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"action": "x", "result": "exploded"}).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_bad_risk_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"action": "x", "risk_level": "nuclear"}).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_non_dict_payload_returns_400(self, client: TestClient) -> None:
        body = json.dumps({"action": "x", "payload": "not a dict"}).encode()
        r = client.post("/api/exec/audit", content=body, headers=_sign(body))
        assert r.status_code == 400

    def test_unsigned_request_rejected(self, client: TestClient) -> None:
        body = json.dumps({"action": "x"}).encode()
        r = client.post("/api/exec/audit", content=body, headers={
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        })
        assert r.status_code == 401


class TestMerkleAudit:

    def test_bad_signature_logged_to_merkle(
        self, client: TestClient, orch: Orchestrator,
    ) -> None:
        body = b'{"command":"echo"}'
        client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: "deadbeef" * 8,
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
        })
        recent = orch._merkle.tail(5)
        refused = [r for r in recent if r.action == "exec.refused.bad_signature"]
        assert len(refused) >= 1
        assert refused[-1].risk_level == "high"

    def test_successful_shell_logged_to_merkle(
        self, client: TestClient, orch: Orchestrator,
    ) -> None:
        body = json.dumps({"command": "git", "args": ["status"]}).encode()
        client.post("/api/exec/shell", content=body, headers=_sign(body))
        recent = orch._merkle.tail(5)
        log_entries = [r for r in recent if r.action == "exec.shell.via_hermes"]
        assert len(log_entries) >= 1
        assert log_entries[-1].agent == "exec_api"
        assert "returncode" in log_entries[-1].payload
