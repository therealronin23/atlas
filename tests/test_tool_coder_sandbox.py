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


# ---------------------------------------------------------------------------
# El jail de test_cmd tiene que poder EJECUTAR los tests
# ---------------------------------------------------------------------------


def test_el_jail_monta_el_runtime_del_interprete(tmp_path, monkeypatch):
    """Sin esto el jail sólo ve `/usr`, y el pytest de esta máquina vive en
    `~/.local` (o en el venv): todo `test_cmd` moría con "No module named
    pytest" y `code()` lo leía como tests en rojo, no como entorno roto.

    Es el mismo fallo que `reproduction.py` pagó el 2026-07-31 —FAILED en 64 ms
    reproduciendo un test que pasaba— y que `validation_runner` ya había
    resuelto. Aquí faltaba, y lo tapaba un flag apagado."""
    from pathlib import Path

    capturado: dict[str, object] = {}

    class _JailFalso:
        def run_command(self, cmd, **kw):
            capturado.update(kw)

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

    monkeypatch.setenv("ATLAS_TOOL_CODER_JAIL", "1")
    monkeypatch.setattr("atlas.core.tool_coder.BwrapJail", lambda: _JailFalso())

    from atlas.core.tool_coder import ToolCoder

    ToolCoder(_ScriptedHubVacio(), repo_root=tmp_path)._run_test_cmd(
        ["python3", "-m", "pytest"], cwd=tmp_path, env={}, use_jail=True,
    )

    montadas = [Path(p) for p in capturado["read_only_paths"]]
    assert montadas, "el jail no monta el runtime: pytest sería inalcanzable"
    assert all(Path("/usr") not in p.parents for p in montadas), (
        "monta descendientes de /usr, que el jail ya expone"
    )


def test_el_jail_no_duplica_lo_que_ya_monta(tmp_path):
    """`/usr` y sus descendientes los aporta el propio jail."""
    from pathlib import Path

    from atlas.core.tool_coder import _runtime_fuera_de_usr

    fuera = _runtime_fuera_de_usr([
        Path("/usr"), Path("/usr/lib/python3.12"), Path("/home/x/.venv"),
    ])

    assert fuera == [Path("/home/x/.venv")]


class _ScriptedHubVacio:
    def infer(self, req):  # pragma: no cover - no se llega a inferir
        raise AssertionError("no debería inferir")

    def infer_for_role(self, role, req):  # pragma: no cover
        raise AssertionError("no debería inferir")
