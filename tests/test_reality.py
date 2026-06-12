"""Reality report tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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

    report = collect_reality(repo_root=root, workspace=workspace)

    assert report["repo"]["version"] == "1.2.3"
    assert report["runtime"]["source_file_count"] == 1
    assert report["runtime"]["test_file_count"] == 1
    assert report["hermes"]["mode"] == "mock"
    assert report["docs"]["status"] == "ok"
    assert any(c["name"] == "self_improvement.cold_update" for c in report["capabilities"])


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
