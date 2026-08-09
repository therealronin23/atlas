"""Los schemas reconstruidos tienen que validar los registros REALES.

Un schema que no valida el fichero que dice describir es decoración. Y estos
tres nacen precisamente de una pérdida: los originales vivían en
`evidence/legacy_exclusive/.../agent_context/schemas/` y desaparecieron
(auditoría 2026-08-09), sin equivalente vivo en el repo.

No se reconstruyeron de memoria. Cada uno sale de la estructura REAL del
registro vivo que le corresponde, y estos tests son la prueba de que describen
el canon que existe y no el que yo imagine:

    claim.schema.yaml    <- evidence_registry.jsonl   (19 filas)
    decision.schema.yaml <- decision_registry.jsonl   (222 filas)
    mission.schema.yaml  <- capability_registry.jsonl (61 filas)

Si un registro cambia y el schema deja de validarlo, el desactualizado es el
SCHEMA: la fuente es el registro.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
jsonschema = pytest.importorskip("jsonschema")

CANON = Path(__file__).resolve().parent.parent / "docs" / "canon"
SCHEMAS = CANON / "schemas"

PARES = [
    ("claim.schema.yaml", "evidence_registry.jsonl"),
    ("decision.schema.yaml", "decision_registry.jsonl"),
    ("mission.schema.yaml", "capability_registry.jsonl"),
]


def _schema(name: str) -> dict:
    path = SCHEMAS / name
    if not path.exists():
        pytest.skip(f"{name} ausente")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    path = CANON / name
    if not path.exists():
        pytest.skip(f"{name} ausente")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.parametrize(("schema_name", "registry_name"), PARES)
def test_el_schema_es_valido(schema_name: str, registry_name: str) -> None:
    jsonschema.Draft202012Validator.check_schema(_schema(schema_name))


@pytest.mark.parametrize(("schema_name", "registry_name"), PARES)
def test_valida_TODAS_las_filas_del_registro_vivo(
    schema_name: str, registry_name: str
) -> None:
    """No una muestra: todas. Un schema que valida el 90% describe otra cosa."""
    validator = jsonschema.Draft202012Validator(_schema(schema_name))
    rows = _rows(registry_name)

    fallos = []
    for row in rows:
        for err in validator.iter_errors(row):
            fallos.append(f"{row.get('id', '?')}: {err.message[:120]}")

    assert not fallos, (
        f"{len(fallos)} de {len(rows)} filas no validan contra {schema_name}. "
        f"Primeros: {fallos[:3]}"
    )


@pytest.mark.parametrize(("schema_name", "registry_name"), PARES)
def test_declara_que_es_reconstruido_y_no_recuperado(
    schema_name: str, registry_name: str
) -> None:
    """La honestidad de procedencia es el punto entero de este ejercicio:
    presentarlos como los originales recuperados sería repetir el error que se
    está corrigiendo."""
    texto = (SCHEMAS / schema_name).read_text(encoding="utf-8")

    assert "RECONSTRUIDO" in texto
    assert "provenance: DERIVED_FROM_LIVE" in texto


def test_los_schemas_rechazan_basura() -> None:
    """Si validara cualquier cosa no estaría validando nada."""
    validator = jsonschema.Draft202012Validator(_schema("claim.schema.yaml"))

    assert list(validator.iter_errors({"id": "sin-lo-demas"}))
    assert list(validator.iter_errors({}))


def test_un_tier_fuera_de_rango_se_rechaza() -> None:
    validator = jsonschema.Draft202012Validator(_schema("claim.schema.yaml"))
    fila = dict(_rows("evidence_registry.jsonl")[0])
    fila["source_tier"] = 99

    assert list(validator.iter_errors(fila))
