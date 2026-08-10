"""Las órdenes documentadas del harness de red-team tienen que poder correrse.

Encontrado el 2026-08-10: `scripts/redteam/README.md` manda usar
`.venv-redteam-garak` y `.venv-redteam-pyrit`, y en esta máquina no existe
ninguno de los dos — hay uno solo, `.venv-redteam`, con garak y pyrit juntos.
Cada ejemplo del documento falla al instante, y las cifras de referencia de su
tabla se obtuvieron con una separación de venvs que ya no está.

Es la familia de defecto que más veces ha aparecido en esta auditoría: **un
documento que afirma algo que la máquina contradice**, sin nada que lo note.
Aquí el coste es peor de lo normal, porque el documento respalda el Apéndice B
del paper.

El test no exige que los venvs existan —una máquina limpia no los tiene, y CI
tampoco— sino la implicación honesta: **si hay algún venv de red-team montado,
el documento tiene que nombrar uno que exista**. Cuando no hay ninguno, no hay
nada que contradecir y se salta.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parent.parent
_README = _RAIZ / "scripts" / "redteam" / "README.md"

#: `.venv-redteam`, `.venv-redteam-garak`, … tal y como aparezcan en el texto.
_NOMBRE = re.compile(r"\.venv-redteam[\w.-]*")


def _venvs_en_disco() -> list[str]:
    return sorted(
        p.name for p in _RAIZ.glob(".venv-redteam*")
        if (p / "bin" / "python").exists()
    )


def _venvs_en_el_documento() -> set[str]:
    return set(_NOMBRE.findall(_README.read_text(encoding="utf-8")))


def test_el_readme_de_redteam_existe() -> None:
    assert _README.is_file()


def test_el_documento_nombra_algun_venv_montado() -> None:
    """Si hay entorno de red-team, el documento tiene que apuntar a él."""
    en_disco = _venvs_en_disco()
    if not en_disco:
        pytest.skip("sin venvs de red-team montados: nada que contradecir")

    nombrados = _venvs_en_el_documento()

    assert nombrados & set(en_disco), (
        f"el documento nombra {sorted(nombrados)} y en disco hay {en_disco}: "
        "cada orden de ejemplo falla con 'no such file or directory'"
    )


def test_el_documento_avisa_cuando_lo_montado_no_es_lo_documentado() -> None:
    """La discrepancia puede ser legítima —el operador reharía los venvs— pero
    no puede ser SILENCIOSA: las cifras de la tabla se midieron con la
    separación intacta y no son reproducibles sin ella."""
    en_disco = set(_venvs_en_disco())
    if not en_disco:
        pytest.skip("sin venvs de red-team montados")

    texto = _README.read_text(encoding="utf-8")
    documentados = {n for n in _venvs_en_el_documento() if n not in en_disco}
    if not documentados:
        return  # documento y máquina coinciden: no hace falta aviso

    assert "ESTADO REAL DE ESTA MÁQUINA" in texto, (
        f"el documento manda usar {sorted(documentados)}, que no existen, "
        f"y no avisa de ello (en disco: {sorted(en_disco)})"
    )
