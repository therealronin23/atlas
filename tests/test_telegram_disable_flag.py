"""ADR-026 — ATLAS_DISABLE_TELEGRAM=1 must skip bot startup."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


class TestTelegramDisableFlag:

    def test_disable_flag_returns_false(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Even with a token set, the flag wins.
        monkeypatch.setenv("ATLAS_DISABLE_TELEGRAM", "1")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-do-not-call-api")
        assert orch.start_telegram_bot() is False
        # Bot thread should not have been spawned
        assert getattr(orch, "_telegram_thread", None) is None

    def test_disable_flag_logs_to_merkle(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_DISABLE_TELEGRAM", "1")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        orch.start_telegram_bot()
        # Find the telegram.skip event with disabled_by_env result
        recent = orch._merkle.tail(10)
        skips = [r for r in recent if r.action == "telegram.skip"
                 and r.result == "disabled_by_env"]
        assert len(skips) >= 1

    def test_disable_flag_off_does_not_block(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # When flag is absent/0, the normal flow runs (will return False
        # because no token, but for the disabled-by-env reason).
        monkeypatch.delenv("ATLAS_DISABLE_TELEGRAM", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        assert orch.start_telegram_bot() is False
        # The skip log should be no_token, not disabled_by_env
        recent = orch._merkle.tail(10)
        no_token = [r for r in recent if r.action == "telegram.skip"
                    and r.result == "no_token"]
        assert len(no_token) >= 1

    @pytest.mark.parametrize("flag_value", ["0", "false", "no", "  ", ""])
    def test_disable_flag_off_variants(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch,
        flag_value: str,
    ) -> None:
        monkeypatch.setenv("ATLAS_DISABLE_TELEGRAM", flag_value)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        # Flag is OFF in all these cases → normal flow runs (no token → False)
        assert orch.start_telegram_bot() is False
        recent = orch._merkle.tail(10)
        # Either no_token (normal flow) — NOT disabled_by_env
        disabled = [r for r in recent if r.action == "telegram.skip"
                    and r.result == "disabled_by_env"]
        assert len(disabled) == 0
