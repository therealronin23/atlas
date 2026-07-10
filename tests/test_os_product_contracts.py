"""Paridad schemas/*.schema.json ↔ espejos pydantic del Product OS (Fase 15).

Mismo patrón que test_os_event_schema.py: la autoridad es el JSON Schema;
un required allí = campo sin default en el modelo, y viceversa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from atlas.business.models import (
    AdaptiveQuestion,
    BusinessCore,
    BusinessEntity,
    CanonicalityMode,
    EntityCandidate,
    EntityKind,
    InputType,
    OnboardingSession,
    QuestionPack,
    SessionStatus,
)
from atlas.fabric.models import (
    CapabilitySpec,
    ConnectionRecipe,
    ConnectorCategory,
    ConnectorHealth,
    ConnectorPack,
    DataClass,
    HealthStatus,
    PolicyEffect,
    PolicyRule,
    RouteType,
)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"

PAIRS: list[tuple[type[BaseModel], str]] = [
    (ConnectionRecipe, "connection_recipe.schema.json"),
    (ConnectorPack, "connector_pack.schema.json"),
    (ConnectorHealth, "connector_health.schema.json"),
    (CapabilitySpec, "capability.schema.json"),
    (PolicyRule, "policy_rule.schema.json"),
    (QuestionPack, "question_pack.schema.json"),
    (OnboardingSession, "onboarding_session.schema.json"),
    (BusinessCore, "business_core.schema.json"),
    (BusinessEntity, "business_entity.schema.json"),
    (EntityCandidate, "entity_candidate.schema.json"),
]


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(("model", "schema_file"), PAIRS,
                         ids=[p[1] for p in PAIRS])
def test_required_parity(model: type[BaseModel], schema_file: str) -> None:
    schema = _schema(schema_file)
    model_required = {
        name for name, f in model.model_fields.items() if f.is_required()
    }
    assert model_required == set(schema["required"]), (
        f"{schema_file}: modelo requiere {sorted(model_required)} "
        f"pero el schema exige {sorted(schema['required'])}"
    )


@pytest.mark.parametrize(("model", "schema_file"), PAIRS,
                         ids=[p[1] for p in PAIRS])
def test_no_extra_model_fields(model: type[BaseModel], schema_file: str) -> None:
    """Todo campo del modelo debe existir en properties del schema."""
    schema = _schema(schema_file)
    extra = set(model.model_fields) - set(schema["properties"])
    assert not extra, f"{schema_file}: campos sin contrato: {sorted(extra)}"


ENUM_CHECKS: list[tuple[type, str, list[str]]] = [
    (RouteType, "connection_recipe.schema.json",
     ["$defs", "route", "enum"]),
    (ConnectorCategory, "connection_recipe.schema.json",
     ["properties", "category", "enum"]),
    (HealthStatus, "connector_health.schema.json",
     ["properties", "status", "enum"]),
    (DataClass, "capability.schema.json",
     ["properties", "data_class", "enum"]),
    (PolicyEffect, "policy_rule.schema.json",
     ["properties", "effect", "enum"]),
    (EntityKind, "business_entity.schema.json",
     ["properties", "kind", "enum"]),
    (CanonicalityMode, "business_core.schema.json",
     ["properties", "canonicality", "properties", "mode", "enum"]),
    (SessionStatus, "onboarding_session.schema.json",
     ["properties", "status", "enum"]),
    (InputType, "question_pack.schema.json",
     ["$defs", "question", "properties", "input_type", "enum"]),
]


@pytest.mark.parametrize(("enum_cls", "schema_file", "path"), ENUM_CHECKS,
                         ids=[c[0].__name__ for c in ENUM_CHECKS])
def test_enum_parity(enum_cls: type, schema_file: str, path: list[str]) -> None:
    node: dict | list = _schema(schema_file)
    for key in path:
        node = node[key]  # type: ignore[index]
    assert {e.value for e in enum_cls} == set(node), (
        f"{enum_cls.__name__} difiere del enum en {schema_file}:{'/'.join(path)}"
    )


def test_ladder_order_is_api_first() -> None:
    """El orden del enum RouteType ES la Connection Ladder: computer_use
    penúltimo, humano último. Si alguien reordena, esto revienta."""
    order = [r.value for r in RouteType]
    assert order[0] == "native_api"
    assert order[-2] == "computer_use"
    assert order[-1] == "human_manual"
    assert order.index("managed_oauth") < order.index("browser_extension_bridge")


def test_entity_kinds_cover_prompt_catalog() -> None:
    """Los 23 kinds del catálogo de producto están todos."""
    expected = {
        "customer", "contact", "company", "supplier", "product", "service",
        "order", "invoice", "receipt", "delivery_note", "stock_item", "task",
        "opportunity", "quote", "project", "case_file", "document",
        "communication", "payment", "event", "note", "risk", "evidence",
    }
    assert {k.value for k in EntityKind} == expected


def test_entity_candidate_review_is_constitutional() -> None:
    """requires_review=False debe ser IMPOSIBLE en candidatos (const true)."""
    schema = _schema("entity_candidate.schema.json")
    assert schema["properties"]["requires_review"]["const"] is True
    with pytest.raises(Exception):
        EntityCandidate(
            candidate_id="cand_x", kind=EntityKind.CUSTOMER, label="X",
            confidence=0.9, source_refs=["src"], proposed_data={},
            requires_review=False,  # type: ignore[arg-type]
        )


def test_question_model_demands_concreteness() -> None:
    """Una pregunta sin why/what/opciones declaradas no valida: la vaguedad
    es un error de contrato, no de estilo."""
    with pytest.raises(Exception):
        AdaptiveQuestion.model_validate({
            "question_id": "vague",
            "label": "¿Cómo funciona tu empresa?",
            "input_type": "text",
        })
