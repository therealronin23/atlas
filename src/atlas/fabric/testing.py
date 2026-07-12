"""ConnectionTestRunner — prueba conexiones en mock/sandbox. Conectores
reales NO existen en Fase 15: pedir modo real devuelve
BLOCKED_BY_MISSING_DEPENDENCY, nunca un éxito fingido."""

from __future__ import annotations

from typing import Any

from atlas.events.emit import emit_event
from atlas.events.store import OsEventStore
from atlas.fabric.health import HealthMonitor
from atlas.fabric.models import HealthIssue, HealthStatus
from atlas.fabric.recipes import RecipeEngine


class ConnectionTestRunner:
    def __init__(
        self,
        recipes: RecipeEngine,
        health: HealthMonitor,
        store: OsEventStore | None = None,
    ) -> None:
        self._recipes = recipes
        self._health = health
        self._store = store

    def test(self, connector_id: str, mode: str = "mock") -> dict[str, Any]:
        recipe = self._recipes.get(connector_id)
        if recipe is None:
            return {"ok": False, "status": "unknown_connector",
                    "connector_id": connector_id}
        if mode == "real":
            self._health.report(
                connector_id, HealthStatus.NEVER_CONNECTED,
                [HealthIssue(code="no_real_connector",
                             detail="Fase 15 no implementa conectores reales")],
            )
            return {
                "ok": False,
                "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "connector_id": connector_id,
                "detail": "no hay conector real implementado; usa mock/sandbox",
            }
        if mode not in {"mock", "sandbox"}:
            return {"ok": False, "status": "invalid_mode", "mode": mode}
        emit_event(
            self._store,
            "connector.test.finished",
            f"Test {mode} de {recipe.human_name}: ruta "
            f"{recipe.recommended_route.value} verificada en simulación",
            actor="connector",
            source="atlas.fabric.testing",
            payload={"connector_id": connector_id, "mode": mode,
                     "route": recipe.recommended_route.value},
        )
        health = self._health.report(connector_id, HealthStatus.CONNECTED,
                                     simulated=True)
        return {
            "ok": True,
            "simulated": True,
            "mode": mode,
            "connector_id": connector_id,
            "health": health.model_dump(mode="json"),
        }
