"""El canon tiene que PARSEAR, y su verificador tiene que decirlo cuando no.

Fallo mío del 2026-08-11, y de los baratos de cometer. Al registrar la
evidencia de ADC-WO-103 dejé un `status_note:` con la comilla de apertura y
**sin la de cierre**: en el heredoc de Python, el cierre del literal se comió
la comilla que tenía que acabar en el YAML.
`docs/canon/implementation_registry.yaml` quedó sin parsear en `main`.

(Escribiendo este mismo docstring volví a pisar el rastrillo: reproducir el
delimitador literal aquí rompió el fichero de test. Se cuenta con palabras.)

Lo grave no fue eso. Fue lo que hizo `check_canon.py` con ello:

    [UNKNOWN_BLOCKING_WORK_ORDER] ... references unknown work order ADC-WO-102
    [UNKNOWN_BLOCKING_WORK_ORDER] ... references unknown work order ADC-WO-103
    ... (doce en total, uno por pregunta de operador)

Doce hallazgos que parecían inconsistencias reales del canon y eran todos el
mismo `INVALID_YAML`, que salía una vez y se perdía entre ellos. **Un error
disfrazado de doce estados normales** — la familia de defectos que más veces
ha aparecido en este repositorio.

Y encima los doce falsos tapaban CUATRO reales que llevaban ahí sin verse:
`ADC-WO-109` marcado READY exigiendo decisión de operador que ya estaba
tomada, `ADC-WO-111` con un estado `PARKED` que no existe en el vocabulario, y
dos linajes sin commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CANON = REPO / "docs" / "canon"


def _check_canon() -> object:
    """`check_canon.py` define dataclasses, y una dataclass necesita que su
    módulo esté en `sys.modules` para resolver anotaciones. Sin el registro,
    importarlo a mano revienta con un `NoneType has no __dict__` que no dice
    nada de la causa."""
    import importlib.util
    import sys

    if "check_canon_mod" in sys.modules:
        return sys.modules["check_canon_mod"]
    spec = importlib.util.spec_from_file_location(
        "check_canon_mod", REPO / "scripts" / "check_canon.py"
    )
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["check_canon_mod"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _yamls() -> list[Path]:
    return sorted(CANON.glob("*.yaml"))


def test_hay_ficheros_yaml_en_el_canon() -> None:
    """Sin esto, el test de abajo pasaría con la carpeta vacía."""
    assert _yamls(), f"no hay YAML en {CANON}"


@pytest.mark.parametrize("ruta", _yamls(), ids=lambda p: p.name)
def test_cada_yaml_del_canon_parsea(ruta: Path) -> None:
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"{ruta.name} no parsea: {exc}")
    assert datos is not None, f"{ruta.name} está vacío"


def test_el_registro_de_implementacion_tiene_work_orders_de_verdad() -> None:
    """Parsear no basta: un YAML válido pero vacío pasaría el test de arriba
    y dejaría a `check_canon` sin nada que cotejar, que es el mismo agujero
    por otra puerta."""
    datos = yaml.safe_load(
        (CANON / "implementation_registry.yaml").read_text(encoding="utf-8")
    )
    work_orders = datos.get("work_orders")
    assert isinstance(work_orders, list) and len(work_orders) >= 30
    assert all(isinstance(w, dict) and w.get("id") for w in work_orders)


def test_ningun_work_order_usa_un_estado_inventado() -> None:
    """`PARKED` no existía en el vocabulario y estaba en el fichero. Es el
    mismo error que cometí hoy en el backlog con `partial`: inventar un
    estado porque describe mejor la situación, y romper a quien lo lee."""
    modulo = _check_canon()

    datos = yaml.safe_load(
        (CANON / "implementation_registry.yaml").read_text(encoding="utf-8")
    )
    invalidos = [
        (w["id"], w.get("status"))
        for w in datos["work_orders"]
        if w.get("status") not in modulo.WORK_ORDER_STATES
    ]
    assert not invalidos, (
        f"estados fuera del vocabulario {sorted(modulo.WORK_ORDER_STATES)}: {invalidos}"
    )


def test_un_registro_que_no_carga_NO_produce_una_cascada_de_falsos() -> None:
    """El arreglo del verificador, probado por su comportamiento y no por su
    código: sin registro cargado, las preguntas de operador NO pueden
    resolverse, y decir doce veces 'work order desconocida' entierra la causa
    real bajo doce síntomas.

    El primer intento de este arreglo usaba `if not work_orders` y rompía dos
    tests que ya existían: un registro **vacío de verdad** y un registro que
    **no se pudo leer** son cosas distintas, y confundirlas es exactamente el
    error que este bloque existe para arreglar. Por eso la señal es
    explícita."""
    modulo = _check_canon()

    preguntas = [
        {"id": f"OPEN-{i}", "blocking_work_order": f"ADC-WO-{100 + i}"}
        for i in range(12)
    ]
    hallazgos: list = []
    modulo._validate_operator_question_links(
        preguntas, {}, hallazgos, registry_loaded=False,
    )

    assert len(hallazgos) == 1, [h.code for h in hallazgos]
    assert hallazgos[0].code == "WORK_ORDER_REGISTRY_UNAVAILABLE"
    assert "12" in hallazgos[0].message

    # Y con el registro cargado sigue cazando la referencia rota de verdad.
    hallazgos = []
    modulo._validate_operator_question_links(
        [{"id": "OPEN-X", "blocking_work_order": "ADC-WO-999"}],
        {"ADC-WO-102": {"id": "ADC-WO-102"}},
        hallazgos,
    )
    assert [h.code for h in hallazgos] == ["UNKNOWN_BLOCKING_WORK_ORDER"]
