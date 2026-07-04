"""
Tests del Claude Code Tool (delegación gobernada al CLI 'claude').

Misma disciplina que test_crawler.py: ExternalFsBridge antes de tocar el
filesystem externo, credenciales requeridas, y auditoría Merkle. Todos los
tests mockean ``subprocess.run`` — nunca se invoca el CLI real.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge
from atlas.tools.claude_code_tool import ClaudeCodeResult, ClaudeCodeTool


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _make_fs_bridge(tmp_path: Path) -> ExternalFsBridge:
    bridge = ExternalFsBridge(extra_roots={str(tmp_path)})
    return bridge


@pytest.fixture
def claude_tool(tmp_path: Path) -> ClaudeCodeTool:
    bridge = _make_fs_bridge(tmp_path)
    return ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)


class TestGovernance:
    def test_blocked_cwd_raises_permission_error(self, tmp_path: Path) -> None:
        bridge = ExternalFsBridge()  # sin roots → fail-closed
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        with pytest.raises(PermissionError, match="ExternalFsBridge"):
            tool.delegate(task="hola", cwd=str(tmp_path / "no-existe"))

    def test_missing_oauth_token_returns_failed_result(self, tmp_path: Path) -> None:
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        with patch.dict(os.environ, {}, clear=True):
            result = tool.delegate(task="hola", cwd=str(tmp_path))
        assert result.success is False
        assert "CLAUDE_CODE_OAUTH_TOKEN" in (result.error or "")


class TestDelegateMocked:
    def test_success_parses_json(self, tmp_path: Path) -> None:
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        payload = json.dumps(
            {
                "is_error": False,
                "result": "todo bien",
                "session_id": "sess-123",
                "total_cost_usd": 0.42,
            }
        )
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "fake"}
        with patch.dict(os.environ, env, clear=True):
            with patch("subprocess.run", return_value=_FakeProc(stdout=payload)) as m:
                result = tool.delegate(task="hola", cwd=str(tmp_path))
        assert result.success is True
        assert result.result_text == "todo bien"
        assert result.session_id == "sess-123"
        assert result.cost_usd == 0.42
        assert result.error is None
        assert m.call_count == 1

    def test_is_error_true_returns_failed(self, tmp_path: Path) -> None:
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        payload = json.dumps(
            {
                "is_error": True,
                "result": "algo salió mal",
                "session_id": "sess-456",
                "total_cost_usd": 0.01,
            }
        )
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "fake"}
        with patch.dict(os.environ, env, clear=True):
            with patch("subprocess.run", return_value=_FakeProc(stdout=payload)):
                result = tool.delegate(task="hola", cwd=str(tmp_path))
        assert result.success is False
        assert result.result_text == "algo salió mal"
        assert result.error == "algo salió mal"
        assert result.session_id == "sess-456"
        assert result.cost_usd == 0.01

    def test_timeout_returns_failed_result(self, tmp_path: Path) -> None:
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "fake"}
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300),
            ):
                result = tool.delegate(task="hola", cwd=str(tmp_path))
        assert result.success is False
        assert "timeout" in (result.error or "").lower()

    def test_malformed_json_returns_failed_result(self, tmp_path: Path) -> None:
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(workspace=tmp_path, fs_bridge=bridge)
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "fake"}
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "subprocess.run", return_value=_FakeProc(stdout="not json")
            ):
                result = tool.delegate(task="hola", cwd=str(tmp_path))
        assert result.success is False
        assert "JSON" in (result.error or "")

    def test_audits_via_merkle(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(tmp_path / "logs")
        bridge = _make_fs_bridge(tmp_path)
        tool = ClaudeCodeTool(
            workspace=tmp_path, fs_bridge=bridge, merkle=merkle
        )
        payload = json.dumps(
            {
                "is_error": False,
                "result": "ok",
                "session_id": "sess-789",
                "total_cost_usd": 0.1,
            }
        )
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "fake"}
        with patch.dict(os.environ, env, clear=True):
            with patch("subprocess.run", return_value=_FakeProc(stdout=payload)):
                tool.delegate(task="hola", cwd=str(tmp_path))
        records = [r for r in merkle.tail(10) if r.action == "claude_code.delegate"]
        assert records
        assert records[-1].result == "ok"
        assert records[-1].payload["cost_usd"] == 0.1
