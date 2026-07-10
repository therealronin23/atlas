"""Tests para atlas_mcp_config y su compatibilidad con load_servers (ADR-035)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from atlas.mcp.trunk_manifest import atlas_mcp_config
from atlas.mcp.config import load_servers, McpServerConfig


class TestAtlasMcpConfig:
    def _config(self) -> list[dict]:
        return atlas_mcp_config(
            save_dir=Path("/save"),
            repo_root=Path("/repo"),
            python="/py",
        )

    def test_returns_one_entry(self) -> None:
        result = self._config()
        assert len(result) == 1

    def test_name_is_atlas_trunk(self) -> None:
        result = self._config()
        assert result[0]["name"] == "atlas-trunk"

    def test_cmd_contains_module_and_paths(self) -> None:
        result = self._config()
        cmd = result[0]["cmd"]
        assert "atlas.mcp.trunk_server" in cmd
        assert "/save" in cmd
        assert "/repo" in cmd

    def test_cmd_uses_provided_python(self) -> None:
        result = self._config()
        assert result[0]["cmd"][0] == "/py"

    def test_read_only_tools_includes_trunk_find(self) -> None:
        result = self._config()
        assert "trunk_find" in result[0]["read_only_tools"]

    def test_read_only_tools_includes_all_navigation_tools(self) -> None:
        result = self._config()
        rot = result[0]["read_only_tools"]
        for expected in [
            "trunk_sectors", "trunk_subsectors", "trunk_tools",
            "trunk_kinds", "trunk_health", "trunk_catalog", "trunk_find",
            "trunk_recommend_stack", "trunk_prepare",
            "list_skills", "get_skill",
            "trunk_list_roots", "trunk_selfcheck",
        ]:
            assert expected in rot, f"missing read_only_tool: {expected}"

    def test_enabled_true(self) -> None:
        result = self._config()
        assert result[0]["enabled"] is True

    def test_timeout_seconds(self) -> None:
        result = self._config()
        assert result[0]["timeout_seconds"] == 30.0


class TestLoadServersCompatibility:
    """Verifica que la config generada sea parseable por load_servers."""

    def test_load_servers_returns_one_mcpserverconfig(self) -> None:
        config = atlas_mcp_config(
            save_dir=Path("/save"),
            repo_root=Path("/repo"),
            python="/py",
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(config, f)
            tmp_path = Path(f.name)

        try:
            servers = load_servers(tmp_path)
            assert len(servers) == 1
            server = servers[0]
            assert isinstance(server, McpServerConfig)
            assert server.name == "atlas-trunk"
        finally:
            tmp_path.unlink(missing_ok=True)


class TestCursorMcpConfig:
    """Cursor config should be launchable even when the MCP client sanitizes env."""

    def test_cursor_trunk_pythonpath_includes_src_and_venv_site_packages(self) -> None:
        config_path = Path(__file__).resolve().parent.parent / ".cursor" / "mcp.json"
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        server = raw["mcpServers"]["atlas-trunk"]
        pythonpath = server["env"]["PYTHONPATH"]

        assert "${workspaceFolder}/src" in pythonpath
        assert "${workspaceFolder}/.venv/lib/python3.12/site-packages" in pythonpath
        assert server["command"] == "${workspaceFolder}/.venv/bin/python"
