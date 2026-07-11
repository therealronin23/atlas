"""ConnectorDiscoveryEngine — stub honesto de Fase 15: descubre rutas desde
las recetas locales; SIN red. Un target desconocido devuelve la escalera
genérica como sugerencia, marcado unknown_target (no finge conocerlo)."""

from __future__ import annotations

from typing import Any

from atlas.fabric.ladder import LADDER
from atlas.fabric.recipes import RecipeEngine


class ConnectorDiscoveryEngine:
    def __init__(self, recipes: RecipeEngine) -> None:
        self._recipes = recipes

    def discover(self, target: str) -> dict[str, Any]:
        normalized = target.strip().lower().replace(" ", "_").replace("-", "_")
        recipe = self._recipes.get(normalized)
        if recipe is None:
            for candidate in self._recipes.all():
                if normalized in candidate.connector_id or (
                    normalized in candidate.human_name.lower()
                ):
                    recipe = candidate
                    break
        if recipe is not None:
            return {
                "status": "recipe_found",
                "connector_id": recipe.connector_id,
                "routes": [recipe.recommended_route.value,
                           *[r.value for r in recipe.fallback_routes]],
                "network_used": False,
            }
        return {
            "status": "unknown_target",
            "target": target,
            "detail": "sin receta local; discovery de red no implementado "
                      "(Fase 16): se sugiere la escalera genérica",
            "generic_ladder": [route.value for route, _ in LADDER],
            "network_used": False,
        }
