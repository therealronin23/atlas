"""Tests de integridad HMAC para pending approvals (Sesion B1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.contracts import Task, TaskSource, TaskStatus
from atlas.core.orchestrator import Orchestrator
from atlas.security.pending_store import compute_pending_mac, wrap_task_payload


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_PENDING_HMAC_KEY", "test-pending-hmac-key")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


class TestPendingHmac:
    def test_roundtrip_persist_load(self, orch: Orchestrator) -> None:
        task = Task(intent="smoke pending", source=TaskSource.CLI)
        task.status = TaskStatus.AWAITING_APPROVAL
        orch._persist_pending_approval(task)
        loaded = orch._load_pending_approval(task.id)
        assert loaded is not None
        assert loaded.id == task.id
        assert loaded.intent == task.intent

    def test_tampered_mac_rejected(self, orch: Orchestrator) -> None:
        task = Task(intent="tamper test", source=TaskSource.CLI)
        task.status = TaskStatus.AWAITING_APPROVAL
        orch._persist_pending_approval(task)
        path = orch._pending_approval_dir / f"{task.id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["mac"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
        assert orch._load_pending_approval(task.id) is None

    def test_legacy_plain_json_rejected(self, orch: Orchestrator) -> None:
        task = Task(intent="legacy", source=TaskSource.CLI)
        path = orch._pending_approval_dir / f"{task.id}.json"
        orch._pending_approval_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(orch._serialize_task(task), ensure_ascii=False),
            encoding="utf-8",
        )
        assert orch._load_pending_approval(task.id) is None

    def test_approve_pending_skips_tampered(self, orch: Orchestrator) -> None:
        task = Task(intent="approve tamper", source=TaskSource.CLI)
        task.status = TaskStatus.AWAITING_APPROVAL
        orch._persist_pending_approval(task)
        path = orch._pending_approval_dir / f"{task.id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["task"]["intent"] = "malicious intent"
        data["mac"] = compute_pending_mac(data["task"])
        # MAC matches altered intent — still loads; test intent change without mac update
        data["task"]["intent"] = "evil"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = orch.approve_pending(task.id, approved=True)
        assert result.get("status") == "unknown"

    def test_pending_store_module_roundtrip(self) -> None:
        task_data = {"id": "t1", "intent": "x", "source": "cli"}
        wrapped = wrap_task_payload(task_data)
        assert wrapped["v"] == 1
        assert wrapped["mac"]
