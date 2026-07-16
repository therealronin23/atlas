"""Tests for atlas doctor diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from atlas.core.doctor import run_diagnostics


class FakeMerkle:
    def __init__(self, ok: bool = True, records: int = 3) -> None:
        self._ok = ok
        self.record_count = records

    def verify_chain(self) -> tuple[bool, str]:
        return (self._ok, "OK" if self._ok else "broken at #2")


class FakeOrch:
    def __init__(
        self,
        tmp_path: Path,
        gov_ok: bool = True,
        chain_ok: bool = True,
        tools: int = 16,
    ) -> None:
        self._merkle = FakeMerkle(ok=chain_ok)
        self._status = SimpleNamespace(
            governance_ok=gov_ok,
            workspace=str(tmp_path),
            tool_count=tools,
        )

    def status(self) -> SimpleNamespace:
        return self._status


class FakeKanban:
    def __init__(self, reachable: bool = True) -> None:
        self._reachable = reachable

    def reachable(self) -> bool:
        return self._reachable


def test_all_green(tmp_path, monkeypatch):
    for k in ("HERMES_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "x")
    orch = FakeOrch(tmp_path)
    report = run_diagnostics(orch, kanban=FakeKanban(reachable=True))
    assert report["status"] == "ok"
    assert report["summary"]["failed"] == 0


def test_corrupt_merkle_degrades(tmp_path):
    orch = FakeOrch(tmp_path, chain_ok=False)
    report = run_diagnostics(orch, kanban=FakeKanban())
    assert report["status"] == "degraded"
    merkle = next(c for c in report["checks"] if c["name"] == "merkle_chain")
    assert merkle["ok"] is False


def test_emergency_governance_degrades(tmp_path):
    orch = FakeOrch(tmp_path, gov_ok=False)
    report = run_diagnostics(orch, kanban=FakeKanban())
    assert report["status"] == "degraded"


def test_missing_env_is_advisory_only(tmp_path, monkeypatch):
    for k in ("HERMES_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    orch = FakeOrch(tmp_path)
    report = run_diagnostics(orch, kanban=FakeKanban())
    env = next(c for c in report["checks"] if c["name"] == "environment")
    assert env["ok"] is False
    assert env["advisory"] is True
    # advisory failure must NOT degrade the aggregate
    assert report["status"] == "ok"


def test_unreachable_twin_is_advisory(tmp_path, monkeypatch):
    for k in ("HERMES_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "x")
    orch = FakeOrch(tmp_path)
    report = run_diagnostics(orch, kanban=FakeKanban(reachable=False))
    twin = next(c for c in report["checks"] if c["name"] == "hermes_twin")
    assert twin["ok"] is False
    assert twin["advisory"] is True
    assert report["status"] == "ok"


def test_unconfigured_twin_is_not_misreported_as_broken_ssh(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("HERMES_KANBAN_TRANSPORT", raising=False)
    monkeypatch.delenv("HERMES_SSH_HOST", raising=False)
    orch = FakeOrch(tmp_path)

    report = run_diagnostics(orch)

    twin = next(c for c in report["checks"] if c["name"] == "hermes_twin")
    assert twin["ok"] is False
    assert twin["advisory"] is True
    assert twin["detail"] == "native kanban transport not configured"
    assert twin["data"] == {"configured": False, "live_verified": False}


def test_environment_reports_presence_without_claiming_every_key_is_required(
    tmp_path, monkeypatch
):
    for key in (
        "HERMES_API_KEY",
        "GROQ_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-present-value")
    orch = FakeOrch(tmp_path)

    report = run_diagnostics(orch, kanban=FakeKanban())

    env = next(c for c in report["checks"] if c["name"] == "environment")
    assert env["ok"] is True
    assert env["detail"] == "integration settings present: OPENROUTER_API_KEY"
    assert "missing:" not in env["detail"]
    assert env["data"]["OPENROUTER_API_KEY"] is True
    assert "synthetic-present-value" not in str(env)


def test_workspace_check_reports_path(tmp_path, monkeypatch):
    for k in ("HERMES_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "x")
    orch = FakeOrch(tmp_path)
    report = run_diagnostics(orch, kanban=FakeKanban())
    ws = next(c for c in report["checks"] if c["name"] == "workspace")
    assert ws["ok"] is True
    assert ws["data"]["path"] == str(tmp_path)
