"""Regression tests for portable agent hooks and local-only workspace state."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _active_patterns(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_codex_capability_hook_resolves_git_root_from_subdirectory() -> None:
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CURSOR_PROJECT_DIR", None)
    env.pop("CODEX_PROJECT_DIR", None)
    hooks = json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT / "ui" / "atlas-shell",
        env=env,
        input="",
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        shell=True,
        executable="/bin/bash",
    )

    assert result.returncode == 0, result.stderr


def test_local_codex_config_and_raw_chat_export_are_ignored() -> None:
    gitignore = _active_patterns(REPO_ROOT / ".gitignore")
    graphifyignore = _active_patterns(REPO_ROOT / ".graphifyignore")

    assert "/.codex/config.toml" in gitignore
    assert "/Diseño UI Atlas.md" in gitignore
    assert "Diseño UI Atlas.md" in graphifyignore


def test_portable_codex_hooks_are_valid_json() -> None:
    hooks = json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    claude = json.loads(
        (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    commands = [
        hook["command"]
        for event in hooks["hooks"].values()
        for group in event
        for hook in group["hooks"]
    ]
    assert any("daemon_idle_guard.sh" in command for command in commands)
    assert any("capability_route_hook.sh" in command for command in commands)
    assert all("/home/" not in command for command in commands)
    assert all("git rev-parse --show-toplevel" in command for command in commands[1:])
    assert hooks["hooks"]["SessionStart"][0] == claude["hooks"]["SessionStart"][0]
