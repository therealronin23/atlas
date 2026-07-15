"""Sector Registry + Objective Registry (Fase 15).

`sector_id` era un string suelto compartido por convención entre
question_packs y connector_packs, sin catálogo que validara que existe.
Este test es el que caza el drift real: todo sector_id usado por los packs
de fixtures/ debe existir en el SectorRegistry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from atlas.business.questions import load_all_packs
from atlas.business.registries import (
    Objective,
    ObjectiveRegistry,
    Sector,
    SectorRegistry,
    unknown_sectors,
)
from atlas.fabric.packs import PackEngine
from atlas.fabric.recipes import RecipeEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = REPO_ROOT / "schemas"
SECTORS_DIR = REPO_ROOT / "fixtures" / "sectors"
OBJECTIVES_DIR = REPO_ROOT / "fixtures" / "objectives"
QUESTION_PACKS_DIR = REPO_ROOT / "fixtures" / "question_packs"
CONNECTOR_PACKS_DIR = REPO_ROOT / "fixtures" / "connector_packs"
RECIPES_DIR = REPO_ROOT / "fixtures" / "connection_recipes"

EXPECTED_SECTORS = {
    "gestoria_fiscal_contable",
    "restauracion_hosteleria",
    "ventas_crm",
    "software_it_seguridad",
    "vida_personal_familia",
}


@pytest.fixture()
def sector_registry() -> SectorRegistry:
    return SectorRegistry(SECTORS_DIR)


@pytest.fixture()
def objective_registry(sector_registry: SectorRegistry) -> ObjectiveRegistry:
    return ObjectiveRegistry(OBJECTIVES_DIR, sector_registry)


# -- Carga sin rechazos -------------------------------------------------------

def test_all_five_sectors_load_without_rejection(sector_registry: SectorRegistry) -> None:
    assert sector_registry.rejected == {}
    assert {s.sector_id for s in sector_registry.all()} == EXPECTED_SECTORS


def test_both_demo_objectives_load_without_rejection(
    objective_registry: ObjectiveRegistry,
) -> None:
    assert objective_registry.rejected == {}
    assert {o.objective_id for o in objective_registry.all()} == {
        "obj_gestoria_filing",
        "obj_restaurant_menu_setup",
    }


# -- El test de valor: caza drift entre packs reales y el catálogo -----------

def test_question_pack_sectors_are_all_registered(sector_registry: SectorRegistry) -> None:
    packs = load_all_packs(QUESTION_PACKS_DIR)
    assert packs, "fixture de question_packs vacío — el test no probaría nada"
    sector_ids = [p.sector_id for p in packs.values()]
    assert unknown_sectors(sector_ids, sector_registry) == []


def test_connector_pack_sectors_are_all_registered(sector_registry: SectorRegistry) -> None:
    recipes = RecipeEngine(RECIPES_DIR)
    packs = PackEngine(CONNECTOR_PACKS_DIR, recipes)
    assert packs.all(), "fixture de connector_packs vacío — el test no probaría nada"
    sector_ids = [p.sector_id for p in packs.all()]
    assert unknown_sectors(sector_ids, sector_registry) == []


# -- Rechazo de objetivo con sector inexistente -------------------------------

def test_objective_with_unknown_sector_is_rejected(
    tmp_path: Path, sector_registry: SectorRegistry,
) -> None:
    objectives_dir = tmp_path / "objectives"
    objectives_dir.mkdir()
    (objectives_dir / "obj_ghost.json").write_text(
        json.dumps({
            "objective_id": "obj_ghost",
            "sector_id": "no_existe_este_sector",
            "label": "Objetivo fantasma",
        }),
        encoding="utf-8",
    )
    registry = ObjectiveRegistry(objectives_dir, sector_registry)
    assert registry.all() == []
    assert "obj_ghost" in registry.rejected
    assert registry.exists("obj_ghost") is False


def test_unknown_sectors_reports_only_missing_ones(sector_registry: SectorRegistry) -> None:
    result = unknown_sectors(
        ["gestoria_fiscal_contable", "sector_que_no_existe"], sector_registry,
    )
    assert result == ["sector_que_no_existe"]


# -- Paridad required↔schema (mismo patrón que test_os_product_contracts.py) -

def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


PAIRS: list[tuple[type[BaseModel], str]] = [
    (Sector, "sector.schema.json"),
    (Objective, "objective.schema.json"),
]


@pytest.mark.parametrize(("model", "schema_file"), PAIRS, ids=[p[1] for p in PAIRS])
def test_required_parity(model: type[BaseModel], schema_file: str) -> None:
    schema = _schema(schema_file)
    model_required = {
        name for name, f in model.model_fields.items() if f.is_required()
    }
    assert model_required == set(schema["required"]), (
        f"{schema_file}: modelo requiere {sorted(model_required)} "
        f"pero el schema exige {sorted(schema['required'])}"
    )


@pytest.mark.parametrize(("model", "schema_file"), PAIRS, ids=[p[1] for p in PAIRS])
def test_no_extra_model_fields(model: type[BaseModel], schema_file: str) -> None:
    schema = _schema(schema_file)
    extra = set(model.model_fields) - set(schema["properties"])
    assert not extra, f"{schema_file}: campos sin contrato: {sorted(extra)}"


# -- Endpoints /sectors y /objectives (paridad propia, no toco test_os_product_contracts.py) -

def test_sectors_and_objectives_endpoints(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from atlas.api.server import create_app
    from atlas.events.store import OsEventStore

    store = OsEventStore(tmp_path / "events.jsonl")
    client = TestClient(
        create_app(
            store=store,
            fixtures_dir=REPO_ROOT / "fixtures",
            business_core_path=tmp_path / "business_core.json",
        ),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )

    sectors_body = client.get("/sectors").json()
    assert sectors_body["count"] == 5
    assert sectors_body["rejected"] == {}

    objectives_body = client.get("/objectives").json()
    assert objectives_body["count"] == 2
    assert objectives_body["rejected"] == {}
