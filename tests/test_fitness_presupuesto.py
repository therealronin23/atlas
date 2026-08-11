"""El banco cuenta lo que va a gastar ANTES de gastarlo.

Medido el 2026-08-11 con dos ejecuciones completas: el corpus entero con tres
tiradas pide ~285 peticiones al proveedor, y los tiers gratuitos conceden
decenas al día — `requests per day` en Groq, `free-models-per-day` en
OpenRouter. **El banco nunca había sido ejecutable así**, y cada `0.0%`
publicado antes estaba leyendo agotamiento de cuota como incapacidad de Atlas.

La sonda que se escribió el 09-ago no puede detectarlo por construcción: gasta
UNA petición, así que responde "¿puedo llamar?" cuando la pregunta es "¿puedo
llamar 285 veces?". Dijo "disponible" minutos antes de que la cadena reventara,
y no mentía. Contra un límite por NÚMERO de peticiones, lo único que funciona
es contarlas antes.

Estos tests fijan las tres formas de que ese cálculo engañe: que subestime,
que recorte por donde no debe, y que deje pasar una configuración que no es una
medición.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fitness_run import (  # noqa: E402
    LLAMADAS_ATLAS,
    LLAMADAS_DESNUDO,
    LLAMADAS_POR_DEFECTO,
    coste_estimado,
    dimensionar_al_presupuesto,
)


# ---------------------------------------------------------------------------
# 1. El coste no puede subestimar
# ---------------------------------------------------------------------------


def test_el_coste_cuenta_las_dos_llamadas_de_toolcoder_y_la_del_desnudo() -> None:
    """Contado en el código, no estimado: ToolCoder hace 1 de planificación más
    hasta `max_iterations=3` del bucle; `DirectModelSolver` hace una."""
    assert LLAMADAS_ATLAS == 4
    assert LLAMADAS_DESNUDO == 1
    assert LLAMADAS_POR_DEFECTO == 5


def test_el_coste_del_corpus_completo_reproduce_lo_medido() -> None:
    """19 defectos x 3 tiradas fue justo lo que reventó dos veces el 11-ago."""
    assert coste_estimado(19, 3) == 285


def test_el_coste_es_una_COTA_no_una_media() -> None:
    """Presupuestar con la media deja al banco a mitad de camino, que es
    exactamente el fallo que este cálculo existe para evitar. Debe crecer
    linealmente y sin descuentos optimistas."""
    assert coste_estimado(10, 2) == coste_estimado(5, 2) * 2
    assert coste_estimado(5, 4) == coste_estimado(5, 2) * 2


@pytest.mark.parametrize("defectos,repeats", [(0, 3), (5, 0), (0, 0)])
def test_una_configuracion_vacia_no_cuesta_nada(defectos: int, repeats: int) -> None:
    assert coste_estimado(defectos, repeats) == 0


# ---------------------------------------------------------------------------
# 2. Recortar por donde SÍ y no por donde NO
# ---------------------------------------------------------------------------


def test_lo_que_cabe_cabe_de_verdad() -> None:
    """La invariante que hace útil todo esto: lo que devuelve no se pasa."""
    for presupuesto in (20, 30, 40, 75, 150, 300):
        muestra, repeats = dimensionar_al_presupuesto(19, presupuesto)
        if muestra:
            assert coste_estimado(muestra, repeats) <= presupuesto


def test_nunca_recorta_por_debajo_de_dos_tiradas() -> None:
    """Una sola tirada NO es una medición: el mismo banco dio 2/3 y 0/3 con el
    mismo código el 2026-08-09. Recortar ahí produce un número que no distingue
    capacidad de suerte, así que se recorta la MUESTRA, que sí es honesto
    mientras se publique cuántos defectos entraron."""
    for presupuesto in range(10, 400, 7):
        _, repeats = dimensionar_al_presupuesto(19, presupuesto)
        assert repeats in (0, 2, 3), f"presupuesto {presupuesto} dio {repeats} tiradas"


def test_con_presupuesto_de_sobra_no_recorta_nada() -> None:
    muestra, repeats = dimensionar_al_presupuesto(19, 1000)

    assert muestra == 19 and repeats == 3


def test_prefiere_tres_tiradas_cuando_caben() -> None:
    """Más repeticiones valen más que más muestra: la varianza entre tiradas es
    lo que separó 'mide capacidad' de 'midió suerte'."""
    muestra, repeats = dimensionar_al_presupuesto(19, 285)

    assert repeats == 3


def test_el_presupuesto_medido_hoy_da_una_configuracion_concreta() -> None:
    """40 peticiones es lo que se consideró seguro contra los tiers gratuitos."""
    assert dimensionar_al_presupuesto(19, 40) == (4, 2)


# ---------------------------------------------------------------------------
# 3. Preferible no medir que publicar algo que no es una medición
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("presupuesto", [0, 5, 10, 25])
def test_si_no_cabe_una_medicion_no_devuelve_una_a_medias(presupuesto: int) -> None:
    """Con menos de 3 defectos x 2 tiradas el resultado no distingue nada.
    Devolver `(0, 0)` obliga a quien llama a abortar en vez de publicar un
    número que parece un resultado."""
    muestra, repeats = dimensionar_al_presupuesto(19, presupuesto)

    assert (muestra, repeats) == (0, 0)


def test_el_umbral_exacto_donde_empieza_a_caber() -> None:
    """3 defectos x 2 tiradas x 5 llamadas = 30, el mínimo que es medición."""
    assert dimensionar_al_presupuesto(19, 29) == (0, 0)
    assert dimensionar_al_presupuesto(19, 30) == (3, 2)


def test_un_corpus_pequeno_no_infla_la_muestra() -> None:
    """Nunca puede devolver más defectos de los que hay."""
    muestra, _ = dimensionar_al_presupuesto(3, 1000)

    assert muestra == 3
