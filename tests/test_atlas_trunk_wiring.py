"""Tests para atlas_mcp_config y su compatibilidad con load_servers (ADR-035)."""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from atlas.mcp.trunk_manifest import atlas_mcp_config
from atlas.mcp.config import load_servers, McpServerConfig
from atlas.mcp.registry import McpRegistry
from atlas.security.sentinel_gate import SentinelGate


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

    def test_generated_atlas_trunk_command_is_governed_native(
        self, tmp_path: Path
    ) -> None:
        """The runtime's generated trunk command must pass Sentinel pre-spawn.

        This binds the producer of ``mcp_servers.json`` to the fail-closed
        native-command boundary, so adding a native Atlas MCP server cannot
        accidentally make its generated configuration unlaunchable.
        """
        repo_root = Path(__file__).resolve().parents[1]
        raw = atlas_mcp_config(
            save_dir=tmp_path / "save",
            repo_root=repo_root,
            python=sys.executable,
        )
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(raw), encoding="utf-8")

        [config] = load_servers(path)

        assert (
            SentinelGate(
                tmp_path / "sentinel", governed_repo_root=repo_root
            ).vet_command(config)
            is None
        )

    def test_atlas_trunk_rejects_spoofed_execution_context(
        self, tmp_path: Path
    ) -> None:
        """A module name alone never proves the subprocess imports Atlas code.

        The native exception is deliberately bound to the running Atlas
        interpreter, the governed checkout and a clean child environment.  A
        user-editable MCP JSON entry cannot swap any one of those values and
        retain the native admission exception.
        """
        repo_root = Path(__file__).resolve().parents[1]
        raw = atlas_mcp_config(
            save_dir=tmp_path / "save",
            repo_root=repo_root,
            python=sys.executable,
        )
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        [config] = load_servers(path)
        gate = SentinelGate(tmp_path / "sentinel", governed_repo_root=repo_root)

        spoofed_executable = replace(
            config,
            cmd=[str(tmp_path / "python"), *config.cmd[1:]],
        )
        symlinked_executable = tmp_path / "python-symlink"
        symlinked_executable.symlink_to(sys.executable)
        downgraded_venv_identity = replace(
            config,
            cmd=[str(symlinked_executable), *config.cmd[1:]],
        )
        spoofed_cwd = replace(config, cwd=str(tmp_path / "shadow"))
        spoofed_repo = replace(
            config,
            cmd=[*config.cmd[:-1], str(tmp_path / "other-repo")],
        )
        injected_import_path = replace(
            config,
            env_extra={"PYTHONPATH": str(tmp_path / "shadow")},
        )

        for altered in (
            spoofed_executable,
            downgraded_venv_identity,
            spoofed_cwd,
            spoofed_repo,
            injected_import_path,
        ):
            assert gate.vet_command(altered) is not None

    def test_native_gate_rejects_a_different_git_checkout_even_if_argv_matches(
        self, tmp_path: Path
    ) -> None:
        """A caller cannot redefine the governed root with an env-like path."""
        actual_root = Path(__file__).resolve().parents[1]
        attacker_root = tmp_path / "attacker-repo"
        attacker_root.mkdir()
        (attacker_root / ".git").mkdir()
        raw = atlas_mcp_config(
            save_dir=tmp_path / "save",
            repo_root=actual_root,
            python=sys.executable,
        )
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        [config] = load_servers(path)
        attacker_config = replace(
            config,
            cwd=str(attacker_root),
            cmd=[*config.cmd[:-1], str(attacker_root)],
        )

        gate = SentinelGate(
            tmp_path / "sentinel", governed_repo_root=attacker_root
        )

        assert gate.vet_command(attacker_config) is not None

    def test_orchestrator_governed_root_ignores_atlas_repo_root_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Git grounding may be configurable; native execution authority is not."""
        from atlas.core.orchestrator import Orchestrator

        attacker_root = tmp_path / "attacker-repo"
        attacker_root.mkdir()
        (attacker_root / ".git").mkdir()
        monkeypatch.setenv("ATLAS_REPO_ROOT", str(attacker_root))

        orch = object.__new__(Orchestrator)

        assert orch._governed_code_root() == Path(__file__).resolve().parents[1]

    def test_relative_save_dir_is_normalized_before_native_admission(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generators must not emit their own command shape as unauthorised."""
        repo_root = Path(__file__).resolve().parents[1]
        monkeypatch.chdir(tmp_path)
        raw = atlas_mcp_config(
            save_dir=Path("state"), repo_root=repo_root, python=sys.executable
        )
        assert raw[0]["cmd"][3] == str((tmp_path / "state").resolve())
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        [config] = load_servers(path)

        assert SentinelGate(tmp_path / "sentinel").vet_command(config) is None

    def test_generated_atlas_trunk_config_reaches_registry_transport_factory(
        self, tmp_path: Path
    ) -> None:
        """Registry must not quarantine its own generated trunk before spawn."""
        repo_root = Path(__file__).resolve().parents[1]
        raw = atlas_mcp_config(
            save_dir=tmp_path / "save",
            repo_root=repo_root,
            python=sys.executable,
        )
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        [config] = load_servers(path)
        attempted: list[str] = []

        def factory(candidate: McpServerConfig) -> object:
            attempted.append(candidate.name)
            raise RuntimeError("test factory stops before any subprocess")

        registry = McpRegistry(
            [config],
            sentinel=SentinelGate(
                tmp_path / "sentinel", governed_repo_root=repo_root
            ),
            transport_factory=factory,  # type: ignore[arg-type]
        )

        registry.start_all()

        assert attempted == ["atlas-trunk"]


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
