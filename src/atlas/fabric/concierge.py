"""ConnectionConcierge — traduce una receta a un plan humano: ruta, pasos,
permisos en lenguaje llano, qué exigirá gate y qué es imposible. El usuario
no necesita saber qué es OAuth ni un scope."""

from __future__ import annotations

from typing import Any

from atlas.fabric.capabilities import get_capability
from atlas.fabric.ladder import route_risk, rung
from atlas.fabric.legal import LegalRegistry
from atlas.fabric.models import ConnectionRecipe
from atlas.fabric.policy import PolicyEngine, PolicyRequest
from atlas.fabric.recipes import RecipeEngine


class ConnectionConcierge:
    def __init__(
        self,
        recipes: RecipeEngine,
        policy: PolicyEngine,
        legal: LegalRegistry | None = None,
    ) -> None:
        self._recipes = recipes
        self._policy = policy
        self._legal = legal

    def plan(self, connector_id: str) -> dict[str, Any] | None:
        recipe = self._recipes.get(connector_id)
        if recipe is None:
            return None
        return self._build_plan(recipe)

    def _build_plan(self, recipe: ConnectionRecipe) -> dict[str, Any]:
        gated: list[dict[str, Any]] = []
        for cap, gate_id in sorted(recipe.gated_capabilities.items()):
            decision = self._policy.evaluate(
                PolicyRequest(
                    capability=cap, connector_id=recipe.connector_id,
                    personal_channel=recipe.personal_channel,
                )
            )
            spec = get_capability(cap)
            gated.append({
                "capability": cap,
                "gate_id": gate_id,
                "policy_decision": decision.decision,
                "risk": spec.risk.value if spec else "high",
                "description": spec.description if spec else "",
            })
        forbidden = [
            {
                "capability": cap,
                "reason": "prohibida por receta: ni con aprobación",
            }
            for cap in sorted(recipe.forbidden_capabilities)
        ]
        platform_terms = None
        if self._legal is not None:
            terms = self._legal.get(recipe.connector_id)
            if terms is not None:
                platform_terms = terms.model_dump(mode="json")
        return {
            "connector_id": recipe.connector_id,
            "human_name": recipe.human_name,
            "category": recipe.category.value,
            "route": {
                "recommended": recipe.recommended_route.value,
                "ladder_rung": rung(recipe.recommended_route),
                "route_risk": route_risk(recipe.recommended_route).value,
                "fallbacks": [r.value for r in recipe.fallback_routes],
            },
            "difficulty": recipe.difficulty.value,
            "default_mode": recipe.default_mode.value,
            "setup_steps": [s.model_dump(mode="json") for s in recipe.setup_steps],
            "granted_now": recipe.capabilities,
            "requires_gate": gated,
            "impossible": forbidden,
            "will": recipe.permissions_explainer.will,
            "will_not": recipe.permissions_explainer.will_not,
            "credential_storage": (
                recipe.credential.storage if recipe.credential else "none"
            ),
            "legal_notes": recipe.legal_notes,
            "platform_terms": platform_terms,
            "simulated": True,
        }
