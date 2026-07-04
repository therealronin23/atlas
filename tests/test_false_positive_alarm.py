"""
Tests — alarma automática de falso positivo: success=True con files_changed
vacío es sospechoso (lección del lote A-D: el incremento C-1 tuvo exactamente
esta forma y nadie lo notó hasta la auditoría manual). AtlasCoder debe marcarlo
explícitamente en vez de dejarlo pasar silencioso.
"""

from __future__ import annotations

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


def test_success_with_empty_files_changed_sets_suspicious_flag(tmp_path):
    """test_cmd pasa sin que se haya aplicado ningún cambio real (ej. ya
    pasaba de antes, o el bloque no ancló nada) → suspicious_no_op=True."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    # Bloque que NO existe en el archivo — no se aplica nada
    sr = "<<<<<<< SEARCH\nno_existe_para_nada\n=======\nnada\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="tarea cuyo bloque no ancla",
        context_files=["foo.py"],
        test_cmd=["true"],  # pasa igual, sin cambios reales
    )

    assert result.success is True
    assert result.files_changed == []
    assert result.suspicious_no_op is True


def test_success_with_real_changes_flag_is_false(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _make_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
    )

    assert result.success is True
    assert result.files_changed == ["foo.py"]
    assert result.suspicious_no_op is False
