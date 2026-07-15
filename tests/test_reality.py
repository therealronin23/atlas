"""Reality report tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from atlas.core.reality import collect_reality
from atlas.interfaces.cli import cli


def _mini_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "atlas" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nversion='1.2.3'\nname='atlas-test'\n"
        "[tool.pytest.ini_options]\naddopts=\"-m 'not computer_use'\"\n",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text("965 tests verdes\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("Alias only\n", encoding="utf-8")
    (root / "ROADMAP.md").write_text("965 tests verdes\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )
    return root


def test_collect_reality_reports_static_facts(tmp_path: Path, monkeypatch) -> None:
    root = _mini_repo(tmp_path)
    workspace = tmp_path / "atlas"
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("HERMES_KANBAN_TRANSPORT", raising=False)
    monkeypatch.delenv("ATLAS_HERMES_LOCAL", raising=False)

    report = collect_reality(repo_root=root, workspace=workspace)

    assert report["repo"]["version"] == "1.2.3"
    assert report["runtime"]["source_file_count"] == 1
    assert report["runtime"]["test_file_count"] == 1
    assert report["hermes"]["mode"] == "mock"
    assert report["hermes"]["configured"] is False
    assert report["hermes"]["live_verified"] is False
    assert report["docs"]["status"] == "ok"
    assert any(c["name"] == "self_improvement.cold_update" for c in report["capabilities"])


def test_collect_reality_prefers_kanban_transport_for_hermes(tmp_path: Path, monkeypatch) -> None:
    root = _mini_repo(tmp_path)
    workspace = tmp_path / "atlas"
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "local")
    monkeypatch.setenv("HERMES_BASE_URL", "https://legacy-hermes.invalid")
    monkeypatch.setenv("HERMES_API_KEY", "legacy-key")

    report = collect_reality(repo_root=root, workspace=workspace)

    assert report["hermes"]["mode"] == "kanban_local"
    assert report["hermes"]["base_url_set"] is True
    assert report["hermes"]["api_key_set"] is True
    assert report["hermes"]["configured"] is True
    assert report["hermes"]["live_verified"] is False
    hermes_capability = next(
        capability
        for capability in report["capabilities"]
        if capability["name"] == "hermes.delegation"
    )
    assert hermes_capability["status"] == "configured"


def test_collect_reality_rejects_incomplete_hermes_ssh_config(tmp_path: Path, monkeypatch) -> None:
    root = _mini_repo(tmp_path)
    workspace = tmp_path / "atlas"
    monkeypatch.setenv("HERMES_KANBAN_TRANSPORT", "ssh")
    monkeypatch.delenv("HERMES_SSH_HOST", raising=False)

    report = collect_reality(repo_root=root, workspace=workspace)

    assert report["hermes"]["mode"] == "kanban_ssh"
    assert report["hermes"]["configured"] is False
    assert "requires HERMES_SSH_HOST" in report["hermes"]["reason"]


def test_capability_plane_degrades_command_execution_without_bwrap(
    tmp_path: Path, monkeypatch,
) -> None:
    from atlas.core import reality

    root = _mini_repo(tmp_path)
    monkeypatch.setattr(
        reality.shutil,
        "which",
        lambda command: None if command == "bwrap" else "/synthetic/bin",
    )

    report = collect_reality(repo_root=root, workspace=tmp_path / "atlas")

    command = next(
        capability
        for capability in report["capabilities"]
        if capability["name"] == "execution.command"
    )
    assert command["status"] == "degraded"
    assert "fail closed" in command["evidence"]


def test_browser_state_degrades_when_expected_playwright_executable_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from atlas.core import reality

    expected = tmp_path / "chromium_headless_shell-999" / "chrome-headless-shell"
    monkeypatch.setattr(reality, "find_spec", lambda name: object() if name == "playwright" else None)
    monkeypatch.setattr(reality, "_playwright_chromium_executable", lambda: (expected, ""))

    state = reality._browser_state()

    assert state["status"] == "degraded"
    assert state["expected_chromium_executable"] == str(expected)
    assert state["expected_chromium_present"] is False
    assert "missing playwright chromium executable" in state["reason"]


def test_browser_state_ready_only_for_expected_playwright_executable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from atlas.core import reality

    expected = tmp_path / "chrome-headless-shell"
    expected.write_text("#!/bin/sh\n", encoding="utf-8")
    expected.chmod(0o755)
    monkeypatch.setattr(reality, "find_spec", lambda name: object() if name == "playwright" else None)
    monkeypatch.setattr(reality, "_playwright_chromium_executable", lambda: (expected, ""))

    state = reality._browser_state()

    assert state["status"] == "ready"
    assert state["expected_chromium_present"] is True


def test_collect_reality_flags_contradictory_doc_counts(
    tmp_path: Path,
) -> None:
    root = _mini_repo(tmp_path)
    (root / "CLAUDE.md").write_text("753 tests\n", encoding="utf-8")

    report = collect_reality(repo_root=root, workspace=tmp_path / "atlas")

    assert report["docs"]["status"] == "stale"
    assert report["status"] == "degraded"
    assert report["docs"]["unique_test_count_claims"] == [753, 965]


def test_reality_cli_json(monkeypatch, tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(root))
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))

    result = CliRunner().invoke(cli, ["reality", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["repo"]["version"] == "1.2.3"
    assert "browser" in payload


def test_reality_cli_strict_exits_nonzero_on_stale_docs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _mini_repo(tmp_path)
    (root / "CLAUDE.md").write_text("753 tests\n", encoding="utf-8")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(root))
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))

    result = CliRunner().invoke(cli, ["reality", "--json", "--strict"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert "docs freshness" in payload["strict_failures"]


def test_check_timeout_default_and_env_override(monkeypatch) -> None:
    from atlas.core.reality import _default_check_timeout

    monkeypatch.delenv("ATLAS_REALITY_TIMEOUT", raising=False)
    assert _default_check_timeout() == 600

    monkeypatch.setenv("ATLAS_REALITY_TIMEOUT", "900")
    assert _default_check_timeout() == 900

    # Valores inválidos caen al default seguro, no rompen el preflight.
    for bad in ("0", "-5", "abc", ""):
        monkeypatch.setenv("ATLAS_REALITY_TIMEOUT", bad)
        assert _default_check_timeout() == 600


def test_capabilities_cli_json(monkeypatch, tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(root))
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))

    result = CliRunner().invoke(cli, ["capabilities", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {item["name"] for item in payload}
    assert "audit.merkle" in names
    assert "browser.computer_use" in names


def test_playwright_chromium_executable_stops_manager(monkeypatch, tmp_path: Path) -> None:
    from atlas.core import reality

    stopped: list[bool] = []
    expected = tmp_path / "chrome"

    class _Starter:
        def start(self) -> SimpleNamespace:
            return SimpleNamespace(
                chromium=SimpleNamespace(executable_path=str(expected)),
                stop=lambda: stopped.append(True),
            )

    monkeypatch.setattr(reality, "find_spec", lambda name: object() if name == "playwright" else None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: _Starter()),
    )

    path, error = reality._playwright_chromium_executable()

    assert path == expected
    assert error == ""
    assert stopped == [True]
