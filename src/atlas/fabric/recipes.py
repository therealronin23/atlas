"""ConnectorRecipeEngine — carga y valida recetas de conexión humanas.

Una receta inválida no se sirve a medias: se excluye y se reporta
(fail-closed sobre el catálogo)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from atlas.fabric.capabilities import get_capability
from atlas.fabric.ladder import ladder_violations
from atlas.fabric.models import ConnectionRecipe


class RecipeProblem(Exception):
    """Receta estructuralmente inválida o insegura."""


def validate_recipe(recipe: ConnectionRecipe) -> list[str]:
    """Reglas semánticas más allá del schema."""
    problems: list[str] = []
    problems.extend(
        ladder_violations(recipe.recommended_route, recipe.fallback_routes)
    )
    overlap = set(recipe.capabilities) & set(recipe.forbidden_capabilities)
    if overlap:
        problems.append(f"capacidades a la vez concedidas y prohibidas: {sorted(overlap)}")
    for cap in [*recipe.capabilities, *recipe.gated_capabilities,
                *recipe.forbidden_capabilities]:
        if get_capability(cap) is None:
            problems.append(f"capacidad fuera de catálogo: {cap}")
    for cap in recipe.capabilities:
        spec = get_capability(cap)
        if spec is not None and spec.gate_required:
            problems.append(
                f"{cap} exige gate en el catálogo: debe ir en gated_capabilities, "
                "no concedida por defecto"
            )
    for action, allowed in recipe.safe_defaults.items():
        if action in {"send", "delete", "publish", "pay", "sign", "file"} and allowed:
            problems.append(f"safe_defaults.{action}=true viola no-outbound-por-defecto")
    return problems


class RecipeEngine:
    def __init__(self, recipes_dir: Path) -> None:
        self._recipes: dict[str, ConnectionRecipe] = {}
        self._rejected: dict[str, list[str]] = {}
        if recipes_dir.exists():
            for path in sorted(recipes_dir.glob("*.recipe.json")):
                try:
                    recipe = ConnectionRecipe.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._rejected[path.stem] = [f"schema: {exc}"]
                    continue
                problems = validate_recipe(recipe)
                if problems:
                    self._rejected[recipe.connector_id] = problems
                else:
                    self._recipes[recipe.connector_id] = recipe

    @property
    def rejected(self) -> dict[str, list[str]]:
        return dict(self._rejected)

    def all(self) -> list[ConnectionRecipe]:
        return list(self._recipes.values())

    def get(self, connector_id: str) -> ConnectionRecipe | None:
        return self._recipes.get(connector_id)

    def catalog(self) -> dict[str, list[dict[str, str]]]:
        """Catálogo humano por categoría (Connection Store)."""
        grouped: dict[str, list[dict[str, str]]] = {}
        for r in self._recipes.values():
            grouped.setdefault(r.category.value, []).append({
                "connector_id": r.connector_id,
                "human_name": r.human_name,
                "difficulty": r.difficulty.value,
                "recommended_route": r.recommended_route.value,
                "default_mode": r.default_mode.value,
            })
        for items in grouped.values():
            items.sort(key=lambda item: item["human_name"])
        return grouped
