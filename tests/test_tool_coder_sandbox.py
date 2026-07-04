"""
ToolCoder + sandbox=True — mismo contrato que AtlasCoder (técnica #6):
aplica en copia aislada, solo sincroniza al éxito, repo real intacto si falla.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.tool_coder import ToolCoder
from tests.test_tool_coder import _ScriptedHub, _tc


def test_sandbox_true_syncs_back_on_success(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"], sandbox=True,
    )
    assert result.success is True
    assert f.read_text() == "x = 2\n"


def test_sandbox_true_leaves_real_repo_untouched_on_failure(tmp_path: Path):
    f = tmp_path / "foo.py"
    original = "x = 1\n"
    f.write_text(original)
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="no_existe", new_str="x")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["false"],
        sandbox=True, max_iterations=1,
    )
    assert result.success is False
    assert f.read_text() == original


def test_sandbox_restores_repo_root(tmp_path: Path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    hub = _ScriptedHub([
        [_tc("str_replace", path="foo.py", old_str="x = 1", new_str="x = 2")],
        None,
    ])
    coder = ToolCoder(hub, repo_root=tmp_path)
    coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"], sandbox=True)
    assert coder._repo_root == tmp_path
