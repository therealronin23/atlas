"""
Tests para el modo sandbox de AtlasCoder (técnica #6 replanteada).

Aplica ediciones en una copia aislada del repo, corre los tests ahí, y solo
sincroniza de vuelta al repo real si el resultado final es éxito — el repo
real nunca se toca en caso de fallo (más fuerte que revert_on_failure, que
sí necesita revertir porque escribe directo).
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder


def _make_hub(response_text: str):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = response_text
    resp.error = None
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def test_code_has_sandbox_parameter():
    sig = inspect.signature(AtlasCoder.code)
    assert "sandbox" in sig.parameters
    assert sig.parameters["sandbox"].default is False


def test_sandbox_true_syncs_back_on_success(tmp_path):
    """Con sandbox=True, los archivos se copian de vuelta al repo real solo
    si el resultado final es success=True."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        sandbox=True,
    )

    assert result.success is True
    assert f.read_text() == "x = 2\n"


def test_sandbox_true_leaves_real_repo_untouched_on_failure(tmp_path):
    """Con sandbox=True y test_cmd que siempre falla, el repo real NO cambia
    — nunca se escribió ahí en absoluto."""
    f = tmp_path / "foo.py"
    original = "x = 1\n"
    f.write_text(original)

    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x pero el test siempre falla",
        context_files=["foo.py"], test_cmd=["false"],
        sandbox=True, max_iterations=1,
    )

    assert result.success is False
    assert f.read_text() == original


def test_sandbox_restores_repo_root_after_run(tmp_path):
    """self._repo_root debe volver al valor original tras el run, sin importar
    éxito o fallo — el sandbox es transitorio, no debe filtrarse a llamadas
    posteriores del mismo AtlasCoder."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        sandbox=True,
    )

    assert coder._repo_root == tmp_path


def test_sandbox_cleans_up_temp_dir(tmp_path, monkeypatch):
    """El directorio temporal del sandbox se borra al terminar (éxito o fallo)."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    created: list = []
    orig_create = coder._create_sandbox

    def spying_create():
        d = orig_create()
        created.append(d)
        return d

    monkeypatch.setattr(coder, "_create_sandbox", spying_create)
    coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        sandbox=True,
    )

    assert len(created) == 1
    assert not created[0].exists()


def test_sandbox_false_default_behavior_unchanged(tmp_path):
    """Sin sandbox (default), escribe directo en repo_root como siempre."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
    )

    assert result.success is True
    assert f.read_text() == "x = 2\n"
