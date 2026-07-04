"""
Tests de verificación — Tarea B (técnica #17, Aider): separar "bloques bien
formados/parseados" de "bloques aplicados" como métricas del CoderResult.
Un modelo puede emitir formato perfecto que no ancla (parsed>applied) o
anclar todo lo que emite (parsed==applied) — medir ambos por separado.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder, CoderResult


def _make_hub(response_text: str):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = response_text
    resp.error = None
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def _sr(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def test_coder_result_has_metrics_fields():
    r = CoderResult(success=True, iterations=1, files_changed=[], test_output="")
    assert hasattr(r, "blocks_parsed")
    assert hasattr(r, "blocks_applied")
    assert r.blocks_parsed == 0
    assert r.blocks_applied == 0


def test_metrics_count_parsed_and_applied(tmp_path):
    """2 bloques bien formados, solo 1 ancla → parsed=2, applied=1."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    two_blocks = _sr("x = 1", "x = 2") + "\n\n" + _sr("no_existe_zz", "nada")
    hub = _make_hub(two_blocks)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="t", context_files=["foo.py"], test_cmd=["true"],
    )

    assert result.success is True
    assert result.blocks_parsed == 2
    assert result.blocks_applied == 1


def test_metrics_all_applied(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\ny = 1\n")
    two_blocks = _sr("x = 1", "x = 2") + "\n\n" + _sr("y = 1", "y = 2")
    hub = _make_hub(two_blocks)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(task="t", context_files=["foo.py"], test_cmd=["true"])

    assert result.blocks_parsed == 2
    assert result.blocks_applied == 2
