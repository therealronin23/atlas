"""Tests de cuarentena para TaskPersistence (mac_mismatch + legacy)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
from atlas.security.pending_store import wrap_task_payload


HMAC_KEY = b"test-key-quarantine"


def _make_tp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskPersistence:
    monkeypatch.setenv("ATLAS_PENDING_HMAC_KEY", HMAC_KEY.decode())
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    pending_dir = tmp_path / "pending"
    pending_dir.mkdir()
    merkle = MagicMock()
    return TaskPersistence(pending_dir=pending_dir, merkle=merkle)


def _write_file(pending_dir: Path, task_id: str, data: dict[str, Any]) -> Path:
    path = pending_dir / f"{task_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestQuarantineMacMismatch:
    def test_tampered_moves_to_quarantine(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        task_data = {"id": "t1", "intent": "x", "source": "cli"}
        envelope = wrap_task_payload(task_data, secret=HMAC_KEY)
        envelope["mac"] = "0" * 64  # corrupt
        _write_file(tp._dir, "t1", envelope)

        result = tp.load("t1")

        assert result is None
        assert not (tp._dir / "t1.json").exists()
        quarantine_files = list(tp._quarantine_dir.glob("t1*.json"))
        assert len(quarantine_files) == 1

    def test_tampered_emits_tamper_detected_and_quarantined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        task_data = {"id": "t2", "intent": "y", "source": "cli"}
        envelope = wrap_task_payload(task_data, secret=HMAC_KEY)
        envelope["mac"] = "a" * 64
        _write_file(tp._dir, "t2", envelope)

        tp.load("t2")

        actions = [call.kwargs["action"] for call in tp._merkle.log.call_args_list]
        assert "approval.tamper_detected" in actions
        assert "approval.quarantined" in actions

    def test_load_all_second_call_no_retrigger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        task_data = {"id": "t3", "intent": "z", "source": "cli"}
        envelope = wrap_task_payload(task_data, secret=HMAC_KEY)
        envelope["mac"] = "b" * 64
        _write_file(tp._dir, "t3", envelope)

        tp.load_all()  # moves to quarantine
        tp._merkle.log.reset_mock()
        tp.load_all()  # file is gone — no new events

        actions = [call.kwargs["action"] for call in tp._merkle.log.call_args_list]
        assert "approval.tamper_detected" not in actions
        assert "approval.quarantined" not in actions


class TestQuarantineLegacy:
    def test_legacy_moves_to_quarantine(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        legacy = {"id": "leg1", "intent": "old format", "source": "cli"}
        _write_file(tp._dir, "leg1", legacy)

        result = tp.load("leg1")

        assert result is None
        assert not (tp._dir / "leg1.json").exists()
        assert (tp._quarantine_dir / "leg1.json").exists()

    def test_legacy_emits_legacy_rejected_and_quarantined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        legacy = {"id": "leg2", "intent": "old", "source": "cli"}
        _write_file(tp._dir, "leg2", legacy)

        tp.load("leg2")

        actions = [call.kwargs["action"] for call in tp._merkle.log.call_args_list]
        assert "approval.legacy_rejected" in actions
        assert "approval.quarantined" in actions
        quarantined_call = next(c for c in tp._merkle.log.call_args_list if c.kwargs["action"] == "approval.quarantined")
        assert quarantined_call.kwargs["payload"]["reason"] == "legacy"


class TestValidFileNotQuarantined:
    def test_valid_mac_loads_normally(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        from atlas.core.contracts import Task, TaskSource, TaskStatus
        task = Task(intent="valid task", source=TaskSource.CLI)
        task.status = TaskStatus.AWAITING_APPROVAL
        task_data = TaskPersistence.serialize(task)
        envelope = wrap_task_payload(task_data, secret=HMAC_KEY)
        _write_file(tp._dir, task.id, envelope)

        loaded = tp.load(task.id)

        assert loaded is not None
        assert loaded.intent == "valid task"
        assert not tp._quarantine_dir.exists()


class TestQuarantineFailureSafe:
    def test_move_failure_does_not_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tp = _make_tp(tmp_path, monkeypatch)
        task_data = {"id": "t5", "intent": "x", "source": "cli"}
        envelope = wrap_task_payload(task_data, secret=HMAC_KEY)
        envelope["mac"] = "c" * 64
        _write_file(tp._dir, "t5", envelope)

        # Make quarantine dir a file so rename fails
        tp._quarantine_dir.touch()

        result = tp.load("t5")
        assert result is None
        actions = [call.kwargs["action"] for call in tp._merkle.log.call_args_list]
        assert "approval.quarantine_failed" in actions
