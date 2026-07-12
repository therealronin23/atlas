"""LegalRegistry — registro central de términos de plataforma (ToS) por
conector. Toda receta con riesgo legal (legal_notes o personal_channel) debe
tener una entrada aquí; recipes_missing_terms() lo audita (fail-visible, no
fail-closed: reporta el hueco, no bloquea)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from atlas.fabric.recipes import RecipeEngine


class PlatformTerms(BaseModel):
    """schemas/platform_terms.schema.json."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    platform: str
    automation_allowed: bool
    terms_url: str | None = None
    notes: str | None = None
    personal_use_only: bool = False


class LegalRegistry:
    def __init__(self, terms_path: Path) -> None:
        self._terms: dict[str, PlatformTerms] = {}
        if terms_path.exists():
            raw = json.loads(terms_path.read_text(encoding="utf-8"))
            for item in raw:
                terms = PlatformTerms.model_validate(item)
                self._terms[terms.connector_id] = terms

    def all(self) -> list[PlatformTerms]:
        return list(self._terms.values())

    def get(self, connector_id: str) -> PlatformTerms | None:
        return self._terms.get(connector_id)

    def exists(self, connector_id: str) -> bool:
        return connector_id in self._terms


def recipes_missing_terms(
    recipes: RecipeEngine, registry: LegalRegistry
) -> list[str]:
    """Connector_id de recetas con riesgo legal (legal_notes != null o
    personal_channel) que no tienen entrada en el LegalRegistry."""
    missing: list[str] = []
    for recipe in recipes.all():
        if recipe.legal_notes is not None or recipe.personal_channel:
            if not registry.exists(recipe.connector_id):
                missing.append(recipe.connector_id)
    return missing
