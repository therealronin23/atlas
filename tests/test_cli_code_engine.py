"""
`atlas code --engine {atlas,tool}` — selección de motor. Default=atlas
(Cónclave, 2026-07-02: decisión reversible, evidencia de ToolCoder aún
limitada a tareas fáciles-medias; flip de default pendiente de la
re-medición con tareas difíciles). Cubre ambos motores, secuencial y
--parallel.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from atlas.core.atlas_coder import CoderResult
from atlas.interfaces.cli import cli


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def test_default_engine_is_atlas_coder_sequential(tmp_path: Path, monkeypatch) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.chdir(repo)
    calls = []

    def fake_code(self, task, files, cmd, max_iterations=3, **kw):
        calls.append("atlas")
        return CoderResult(success=True, iterations=1, files_changed=[], test_output="")

    with patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code), \
         patch("atlas.core.inference_hub.InferenceHub.__init__", return_value=None):
        result = CliRunner().invoke(cli, ["code", "tarea", "-t", "true"])

    assert calls == ["atlas"]
    assert result.exit_code == 0


def test_engine_tool_selects_tool_coder_sequential(tmp_path: Path, monkeypatch) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.chdir(repo)
    calls = []

    def fake_code(self, task, files, cmd, max_iterations=3, **kw):
        calls.append("tool")
        return CoderResult(success=True, iterations=1, files_changed=[], test_output="")

    with patch("atlas.core.tool_coder.ToolCoder.code", fake_code), \
         patch("atlas.core.inference_hub.InferenceHub.__init__", return_value=None):
        result = CliRunner().invoke(cli, ["code", "tarea", "-t", "true", "--engine", "tool"])

    assert calls == ["tool"]
    assert result.exit_code == 0


def test_engine_tool_selects_tool_coder_parallel(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    factories: list = []

    class _FakePC:
        def __init__(self, *, repo_root, coder_factory=None, **kw):
            factories.append(coder_factory)

        def run(self, *a, **kw):
            from atlas.core.parallel_coder import ParallelCoderResult
            return ParallelCoderResult(subtasks_total=1, subtasks_passed=1, subtasks_failed=0, results=[])

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_worker = [(Provider(
        name="fake", level=InferenceLevel.L1, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env=None,
    ), "")]

    with patch("atlas.core.parallel_coder.ParallelCoder", _FakePC), \
         patch("atlas.core.parallel_coder.discover_workers", return_value=fake_worker):
        result = CliRunner().invoke(
            cli, ["code", "tarea", "-t", "true", "--parallel", "--engine", "tool"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert factories and factories[0] is not None
