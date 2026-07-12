"""LegalRegistry — registro central de términos de plataforma (ToS) por
conector (gap #10). Contracts-first: fixture + schema son la verdad."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.fabric.concierge import ConnectionConcierge
from atlas.fabric.legal import LegalRegistry, PlatformTerms, recipes_missing_terms
from atlas.fabric.policy import PolicyEngine
from atlas.fabric.recipes import RecipeEngine

REPO = Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO / "fixtures" / "connection_recipes"
TERMS_PATH = REPO / "fixtures" / "legal" / "platform_terms.json"
SCHEMA_PATH = REPO / "schemas" / "platform_terms.schema.json"


@pytest.fixture()
def registry() -> LegalRegistry:
    return LegalRegistry(TERMS_PATH)


@pytest.fixture()
def recipes() -> RecipeEngine:
    return RecipeEngine(RECIPES_DIR)


def test_fixture_loads_without_errors_and_resolves_the_three_entries(
    registry: LegalRegistry,
) -> None:
    for connector_id in (
        "whatsapp_business_platform",
        "whatsapp_personal_import",
        "odoo_erp",
    ):
        terms = registry.get(connector_id)
        assert terms is not None, connector_id
        assert isinstance(terms, PlatformTerms)
        assert registry.exists(connector_id)


def test_no_recipe_with_legal_risk_is_missing_terms(
    recipes: RecipeEngine, registry: LegalRegistry
) -> None:
    """Test de valor: toda receta con riesgo legal (legal_notes o
    personal_channel) declara su entrada en el LegalRegistry. Caza el gap."""
    assert recipes_missing_terms(recipes, registry) == []


def test_recipes_missing_terms_catches_the_gap(recipes: RecipeEngine) -> None:
    """Un registro sin la entrada de whatsapp_personal_import sí lo caza."""
    empty_registry = LegalRegistry(REPO / "fixtures" / "legal" / "does_not_exist.json")
    missing = recipes_missing_terms(recipes, empty_registry)
    assert "whatsapp_personal_import" in missing
    assert "whatsapp_business_platform" in missing


def test_whatsapp_personal_import_forbids_automation(registry: LegalRegistry) -> None:
    terms = registry.get("whatsapp_personal_import")
    assert terms is not None
    assert terms.automation_allowed is False
    assert terms.personal_use_only is True


def test_model_mirrors_json_schema_required_fields() -> None:
    """Paridad modelo↔schema: todo campo required del JSON Schema es
    obligatorio en el modelo (sin default) y viceversa."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_required = set(schema["required"])
    model_required = {
        name for name, f in PlatformTerms.model_fields.items() if f.is_required()
    }
    assert schema_required == model_required
    assert set(schema["properties"]) == set(PlatformTerms.model_fields)


def test_concierge_with_legal_registry_includes_platform_terms(
    recipes: RecipeEngine, registry: LegalRegistry
) -> None:
    concierge = ConnectionConcierge(recipes, PolicyEngine(), registry)
    plan = concierge.plan("whatsapp_business_platform")
    assert plan is not None
    assert plan["platform_terms"] is not None
    assert plan["platform_terms"]["connector_id"] == "whatsapp_business_platform"
    assert plan["platform_terms"]["automation_allowed"] is True


def test_concierge_without_legal_registry_has_null_platform_terms(
    recipes: RecipeEngine,
) -> None:
    concierge = ConnectionConcierge(recipes, PolicyEngine())
    plan = concierge.plan("whatsapp_business_platform")
    assert plan is not None
    assert plan["platform_terms"] is None
