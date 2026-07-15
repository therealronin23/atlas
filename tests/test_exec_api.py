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
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas.core.orchestrator import Orchestrator
from atlas.interfaces.exec_api import (
    HEADER_NONCE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    build_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SECRET = "test-secret-hermes-key-at-least-32-bytes"


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


def _sign(
    body: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    nonce = nonce or uuid4().hex
    signed = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body
    sig = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return {
        HEADER_SIGNATURE: sig,
        HEADER_TIMESTAMP: timestamp,
        HEADER_NONCE: nonce,
    }


# ---------------------------------------------------------------------------
# HMAC auth
# ---------------------------------------------------------------------------


class TestHmacAuth:

    def test_missing_signature_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo", "args": ["hi"]}).encode()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
            HEADER_NONCE: uuid4().hex,
        })
        assert r.status_code == 401

    def test_bad_signature_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: "deadbeef" * 8,
            HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
            HEADER_NONCE: uuid4().hex,
        })
        assert r.status_code == 401

    def test_stale_timestamp_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        stale_ts = "2020-01-01T00:00:00+00:00"
        r = client.post(
            "/api/exec/shell", content=body, headers=_sign(body, timestamp=stale_ts)
        )
        assert r.status_code == 401

    def test_missing_timestamp_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = client.post("/api/exec/shell", content=body, headers={
            HEADER_SIGNATURE: sig,
            HEADER_NONCE: uuid4().hex,
        })
        assert r.status_code == 401

    def test_naive_timestamp_returns_401_not_500(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        naive = datetime.now().isoformat()
        r = client.post(
            "/api/exec/shell", content=body, headers=_sign(body, timestamp=naive)
        )
        assert r.status_code == 401

    def test_missing_nonce_returns_401(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        timestamp = datetime.now(timezone.utc).isoformat()
        signed = timestamp.encode() + b"\n\n" + body
        signature = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
        r = client.post(
            "/api/exec/shell",
            content=body,
            headers={HEADER_SIGNATURE: signature, HEADER_TIMESTAMP: timestamp},
        )
        assert r.status_code == 401

    def test_timestamp_is_covered_by_signature(self, client: TestClient) -> None:
        body = json.dumps({"command": "echo"}).encode()
        signed_headers = _sign(body)
        signed_headers[HEADER_TIMESTAMP] = datetime.now(timezone.utc).isoformat()
        r = client.post("/api/exec/shell", content=body, headers=signed_headers)
        assert r.status_code == 401

    def test_nonce_cannot_be_replayed(self, client: TestClient) -> None:
        body = b"not json"
        headers = _sign(body)
        first = client.post("/api/exec/shell", content=body, headers=headers)
        second = client.post("/api/exec/shell", content=body, headers=headers)
        assert first.status_code == 400
        assert second.status_code == 401

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

    def test_weak_secret_returns_503(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HERMES_API_KEY", "too-short")
        app = FastAPI()
        app.include_router(build_router(lambda: orch))
        c = TestClient(app)
        body = b"{}"
        r = c.post(
            "/api/exec/health",
            content=body,
            headers={
                HEADER_SIGNATURE: "x" * 64,
                HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
                HEADER_NONCE: uuid4().hex,
            },
        )
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
# /api/exec/health
# ---------------------------------------------------------------------------


class TestExecHealth:

    def test_signed_health_reports_live_atlas_state(self, client: TestClient) -> None:
        body = b"{}"
        r = client.post("/api/exec/health", content=body, headers=_sign(body))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["merkle_chain_ok"] is True
        assert data["governance_ok"] is True
        assert "version" in data

    def test_unsigned_health_is_rejected(self, client: TestClient) -> None:
        r = client.post("/api/exec/health", content=b"{}")
        assert r.status_code == 401


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

    def test_intent_grounds_git_log_not_hallucination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ADR-031 twin seal: a factual intent delegated by Hermes returns the
        REAL git history (grounding), not an invented one.

        Regression for the production bug found in the live twin smoke: git
        grounding ran in the workspace (`~/atlas`, NOT a git repo) so every git
        question returned `fatal: not a git repository`. The fix points git at
        ATLAS_REPO_ROOT via `git -C`. Here we seed a tmp repo as that root and
        assert its exact commit subject flows back through /api/exec/intent."""
        import subprocess

        repo = tmp_path / "code-repo"
        repo.mkdir()
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "exec-test", "GIT_AUTHOR_EMAIL": "e@t.local",
            "GIT_COMMITTER_NAME": "exec-test", "GIT_COMMITTER_EMAIL": "e@t.local",
        }
        for args in (
            ["init", "-q"],
            ["commit", "-q", "--allow-empty", "-m", "grounding marker commit"],
        ):
            subprocess.run(["git", *args], cwd=repo, check=True,
                           capture_output=True, env=env)

        # Repo root must be set BEFORE building the Orchestrator: git_inspect_root
        # (the SEC-01 `-C` allowlist target) is captured at construction.
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
        monkeypatch.setenv("HERMES_API_KEY", SECRET)
        monkeypatch.setenv("ATLAS_REPO_ROOT", str(repo))
        orch = Orchestrator(workspace=tmp_path / "atlas")
        app = FastAPI()
        app.include_router(build_router(lambda: orch))
        client = TestClient(app)

        body = json.dumps({"intent": "dame los últimos commits"}).encode()
        r = client.post("/api/exec/intent", content=body, headers=_sign(body))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "done"
        assert data["tool"] == "git.log"
        blob = json.dumps(data["result"], ensure_ascii=False)
        assert "grounding marker commit" in blob
        # Provenance: the result must carry the REAL repo_root so the twin
        # (Hermes) never has to invent a path. Regression for the live bug
        # where the bot confabulated `/home/rocio/Atlas-OS`.
        assert data["result"].get("repo_root") == str(repo.resolve())


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
            HEADER_NONCE: uuid4().hex,
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
